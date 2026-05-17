import uuid
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.constants.edge_taxonomy import NEGATIVE_OUTCOME_TYPES, eligible_targets
from app.constants.ui_screen_taxonomy import normalize_screen_type
from app.model_providers.schemas import CandidateEdge, ActionSequenceStepEdge, EdgeContextParameter
from app.services.candidate_edge_classification import classify_edge_kind, classify_scenario_role
from app.services.candidate_edge_gates import hard_gate_before_targets, hard_gate_per_transition
from app.services.candidate_edge_scoring import apply_many_compatible_targets_penalty, score_candidate_edge
from app.services.candidate_edge_thresholds import (
    classify_confidence,
    derive_edge_class,
    should_keep_edge,
)


def _generate_edge_id(run_id: str) -> str:
    return f"edge_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


def _extract_specific_values(text_corpus: str) -> List[str]:
    """Generic helper to extract potential times, dates, slot values from target text."""
    values = []
    times = re.findall(r"\b\d{1,2}[:\.]\d{2}\b", text_corpus)
    values.extend(times)
    dates = re.findall(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2}\b",
        text_corpus,
    )
    values.extend(dates)
    return [v.lower() for v in values]


def _step_role_for_step_type(step_type: str) -> str:
    mapping = {
        "enter_input": "input",
        "select_option": "select_option",
        "toggle_option": "select_option",
        "invoke_action": "commit",
        "navigate": "navigate",
        "open": "navigate",
        "close": "cancel",
        "confirm": "confirm",
        "cancel": "cancel",
        "upload": "input",
    }
    return mapping.get(step_type, "commit")


def _template_action_sequence(
    state_id: str,
    group_id: Optional[str],
    intent_id: Optional[str],
    intent: Dict[str, Any],
) -> Optional[List[ActionSequenceStepEdge]]:
    tmpls = intent.get("local_action_sequence_templates") or []
    if not tmpls:
        return None
    tmpl = tmpls[0]
    steps_in = tmpl.get("steps") or []
    if not steps_in:
        return None

    seq: List[ActionSequenceStepEdge] = []
    for raw in steps_in:
        ty = raw.get("step_type") or "invoke_action"
        role = _step_role_for_step_type(str(ty))
        texts = raw.get("text") or []
        seq.append(
            ActionSequenceStepEdge(
                source_state=state_id,
                source_group_id=group_id,
                source_screen_intent_id=intent_id,
                source_action_id=raw.get("source_action_id"),
                source_element_id=raw.get("source_element_id"),
                action_role=role,
                action_text=list(texts) if texts else [],
            )
        )
    return seq


def _intent_has_evidence(intent: Dict[str, Any]) -> bool:
    return bool(intent.get("evidence_refs")) or bool(intent.get("evidence"))


def _commit_primary_texts(intent: Dict[str, Any]) -> List[str]:
    act = intent.get("commit_action") or intent.get("primary_action") or {}
    return list(act.get("text") or [])


def _template_specific_value_match(seq: List[ActionSequenceStepEdge], target_values: List[str]) -> bool:
    if not target_values:
        return False
    for step in seq:
        blob = " ".join(step.action_text).lower()
        if any(v in blob for v in target_values):
            return True
    return False


def _serialize_steps(seq: List[ActionSequenceStepEdge]) -> List[Dict[str, Any]]:
    return [s.model_dump() for s in seq]


def _merge_core_key(edge: Dict[str, Any]) -> Tuple[Any, ...]:
    seq = edge.get("action_sequence") or []
    intent_id = seq[0].get("source_screen_intent_id") if seq else None
    return (edge["from_state"], edge["to_state"], edge["edge_kind"], intent_id)


def _action_sequence_signature(seq: Any) -> Tuple[Any, ...]:
    return tuple(
        (
            s.get("action_role"),
            tuple(s.get("action_text") or []),
            s.get("source_action_id"),
            s.get("source_element_id"),
        )
        for s in (seq or [])
    )


def _merge_candidate_edges(candidate_edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for edge in candidate_edges:
        groups[_merge_core_key(edge)].append(edge)

    merged: List[Dict[str, Any]] = []
    for bucket in groups.values():
        bucket_sorted = sorted(bucket, key=lambda e: (-float(e.get("edge_score", 0.0)),))
        primary = dict(bucket_sorted[0])
        sigs = {_action_sequence_signature(primary.get("action_sequence"))}
        alts: List[Any] = []
        for other in bucket_sorted[1:]:
            sig = _action_sequence_signature(other.get("action_sequence"))
            if sig in sigs:
                continue
            sigs.add(sig)
            alts.append(other.get("action_sequence") or [])
        if alts:
            primary["alternative_action_sequences"] = alts
        merged.append(primary)
    return merged


def resolve_candidate_edges(run_id: str, flow_state_cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deterministic candidate edges from validated screen intents (hydrated catalogue).

    Pipeline: Layer 1 hard gates → Layer 2 score (0–100) → multiplicity adjustment →
    Layer 3 class thresholds + confidence → merge alternative sequences.
    """
    candidate_edges: List[Dict[str, Any]] = []

    for state in flow_state_cards:
        state_id = state.get("state_id")
        outcome_type = state.get("outcome_state_type", "neutral")
        if outcome_type == "normal":
            outcome_type = "neutral"
        intents = state.get("screen_behaviour_intents", [])
        source_screen = normalize_screen_type(state.get("screen_type"))
        source_upload_order = state.get("upload_order")
        source_vis = state.get("visible_text") or []
        source_corpus = " ".join(source_vis).lower()
        source_ps = str(state.get("presentation_scope") or "unknown")

        if not intents:
            continue

        for intent in intents:
            intent_kind = intent.get("intent_kind")
            if intent_kind in ("informative", "data_entry") or not intent_kind:
                continue

            if not hard_gate_before_targets(intent).ok:
                continue

            eligible_outcomes = eligible_targets(intent_kind)
            intent_id = intent.get("screen_intent_id")
            group_id = intent.get("source_group_id")
            intent_confidence = str(intent.get("confidence") or "medium")
            validation_confidence = str(intent.get("validation_confidence") or "medium")

            tmpl_seq = _template_action_sequence(state_id, group_id, intent_id, intent)

            commit_act = intent.get("commit_action") or intent.get("primary_action")
            eligible_actions: List[tuple[str, Dict[str, Any]]] = []
            if commit_act:
                eligible_actions.append(("commit", commit_act))
            for sec in intent.get("secondary_actions") or []:
                sec_text = " ".join(sec.get("text", []) or []).lower()
                if any(w in sec_text for w in ("cancel", "confirm", "close")):
                    eligible_actions.append(("cancel_confirm", sec))

            options = intent.get("selection_options") or []

            for target in flow_state_cards:
                target_id = target.get("state_id")
                if target_id == state_id:
                    continue

                target_outcome = target.get("outcome_state_type", "neutral")
                if target_outcome == "normal":
                    target_outcome = "neutral"
                if target_outcome not in eligible_outcomes:
                    continue

                target_screen = normalize_screen_type(target.get("screen_type"))

                gate_t = hard_gate_per_transition(
                    intent_kind=intent_kind,
                    source_outcome=outcome_type,
                    source_card=state,
                    target_card=target,
                    source_screen=source_screen,
                    target_screen=target_screen,
                )
                if not gate_t.ok:
                    continue

                target_texts = (target.get("visible_text") or []) + (target.get("feedback_texts") or [])
                target_corpus = " ".join(target_texts).lower()
                target_values = _extract_specific_values(target_corpus)
                target_upload_order = target.get("upload_order")
                tgt_pres = str(target.get("presentation_scope") or "unknown")

                edge_kind = classify_edge_kind(intent_kind, outcome_type, target_outcome)
                scenario_role = classify_scenario_role(
                    intent_kind, outcome_type, target_outcome, target_screen=target_screen
                )

                if tmpl_seq:
                    cp: List[EdgeContextParameter] = []
                    ambiguous_sel = False
                    if (
                        intent_kind == "selection"
                        and len(options) > 1
                        and target_outcome not in NEGATIVE_OUTCOME_TYPES
                    ):
                        ambiguous_sel = True
                        cp.append(
                            EdgeContextParameter(
                                name="ambiguous_selection_requires_evidence",
                                value="multiple_options_without_target_bind",
                                evidence=[f"group={group_id}", f"intent={intent_id}"],
                            )
                        )

                    main_texts = _commit_primary_texts(intent)
                    if not main_texts and tmpl_seq:
                        main_texts = [t for step in tmpl_seq for t in step.action_text]

                    specific_matched = _template_specific_value_match(tmpl_seq, target_values)

                    sr = score_candidate_edge(
                        intent_kind=intent_kind,
                        intent_confidence=intent_confidence,
                        validation_confidence=validation_confidence,
                        source_outcome=outcome_type,
                        target_outcome=target_outcome,
                        edge_kind=edge_kind,
                        source_screen=source_screen,
                        target_screen=target_screen,
                        source_upload_order=source_upload_order,
                        target_upload_order=target_upload_order,
                        source_corpus=source_corpus,
                        target_corpus=target_corpus,
                        source_visible_texts=list(source_vis),
                        target_visible_texts=list(target.get("visible_text") or []),
                        source_screen_purpose=str(state.get("screen_purpose") or ""),
                        target_screen_purpose=str(target.get("screen_purpose") or ""),
                        source_domain=state.get("domain"),
                        target_domain=target.get("domain"),
                        source_presentation_scope=source_ps,
                        target_presentation_scope=tgt_pres,
                        uses_template_sequence=True,
                        action_steps=_serialize_steps(tmpl_seq),
                        source_group_id=group_id,
                        source_screen_intent_id=intent_id,
                        main_action_texts=main_texts,
                        specific_value_matched=specific_matched,
                        target_has_extracted_specific_values=bool(target_values),
                        ambiguous_selection=ambiguous_sel,
                        unresolved_selection=False,
                        intent_has_evidence=_intent_has_evidence(intent),
                        unordered_images_allowed=settings.UNORDERED_IMAGES_ALLOWED,
                    )

                    rf = list(sr.risk_flags)
                    edge = CandidateEdge(
                        edge_id=_generate_edge_id(run_id),
                        from_state=state_id or "",
                        to_state=target_id or "",
                        edge_kind=edge_kind,
                        scenario_role=scenario_role,
                        action_sequence=tmpl_seq,
                        context_parameters=cp,
                        source_visible_evidence=state.get("visible_text") or [],
                        target_visible_evidence=target.get("visible_text") or [],
                        confidence="medium",
                        edge_score=float(sr.value),
                        edge_score_reasons=sr.reasons,
                        edge_risk_flags=rf,
                    )
                    dumped = edge.model_dump()
                    dumped["_resolver_meta"] = {
                        "intent_kind": intent_kind,
                        "source_outcome": outcome_type,
                        "target_outcome": target_outcome,
                    }
                    candidate_edges.append(dumped)
                    continue

                if not eligible_actions:
                    continue

                for role_type, main_action in eligible_actions:
                    main_text = main_action.get("text") or []
                    commit_action_id = main_action.get("action_id")

                    action_steps: List[ActionSequenceStepEdge] = []
                    ctx_params: List[EdgeContextParameter] = []

                    ambiguous_sel = False
                    unresolved_sel = False
                    specific_matched = False

                    if target_outcome in NEGATIVE_OUTCOME_TYPES and target_values:
                        valid_option = None
                        for opt in options:
                            opt_text_list = opt.get("option_text") or opt.get("text") or []
                            opt_text = " ".join(opt_text_list).lower()
                            if any(v in opt_text or opt_text in v for v in target_values):
                                valid_option = opt
                                break

                        if not valid_option:
                            continue

                        specific_matched = True
                        opt_action_id = valid_option.get("option_action_id")
                        opt_el_id = valid_option.get("option_element_id")
                        action_steps = [
                            ActionSequenceStepEdge(
                                source_state=state_id or "",
                                source_group_id=group_id,
                                source_screen_intent_id=intent_id,
                                source_action_id=opt_action_id,
                                source_element_id=opt_el_id,
                                action_role="select_option",
                                action_text=valid_option.get("option_text") or valid_option.get("text") or [],
                            ),
                            ActionSequenceStepEdge(
                                source_state=state_id or "",
                                source_group_id=group_id,
                                source_screen_intent_id=intent_id,
                                source_action_id=commit_action_id,
                                source_element_id=None,
                                action_role="commit" if role_type == "commit" else "cancel",
                                action_text=main_text,
                            ),
                        ]
                    elif (
                        target_outcome == "success"
                        or (
                            outcome_type == "neutral"
                            and target_outcome == "neutral"
                            and target_screen != "landing"
                        )
                    ) and intent_kind == "selection" and len(options) > 1:
                        unresolved_sel = True
                        action_steps = [
                            ActionSequenceStepEdge(
                                source_state=state_id or "",
                                source_group_id=group_id,
                                source_screen_intent_id=intent_id,
                                source_action_id=commit_action_id,
                                source_element_id=None,
                                action_role="commit",
                                action_text=main_text,
                            )
                        ]
                        ctx_params.append(
                            EdgeContextParameter(
                                name="unresolved_selection_option",
                                value="no_option_bind_without_target_specific_evidence",
                                evidence=[
                                    " ".join(o.get("option_text") or o.get("text") or []).strip()
                                    for o in options[:8]
                                ],
                            )
                        )
                    elif (
                        (
                            target_outcome == "success"
                            or (
                                outcome_type == "neutral"
                                and target_outcome == "neutral"
                                and target_screen != "landing"
                            )
                        )
                        and intent_kind == "selection"
                        and len(options) == 1
                    ):
                        solitary = options[0]
                        solitary_action_id = solitary.get("option_action_id")
                        solitary_el_id = solitary.get("option_element_id")
                        action_steps = [
                            ActionSequenceStepEdge(
                                source_state=state_id or "",
                                source_group_id=group_id,
                                source_screen_intent_id=intent_id,
                                source_action_id=solitary_action_id,
                                source_element_id=solitary_el_id,
                                action_role="select_option",
                                action_text=solitary.get("option_text") or solitary.get("text") or [],
                            ),
                            ActionSequenceStepEdge(
                                source_state=state_id or "",
                                source_group_id=group_id,
                                source_screen_intent_id=intent_id,
                                source_action_id=commit_action_id,
                                source_element_id=None,
                                action_role="commit",
                                action_text=main_text,
                            ),
                        ]
                    else:
                        action_steps = [
                            ActionSequenceStepEdge(
                                source_state=state_id or "",
                                source_group_id=group_id,
                                source_screen_intent_id=intent_id,
                                source_action_id=commit_action_id,
                                source_element_id=None,
                                action_role="commit" if role_type == "commit" else "cancel",
                                action_text=main_text,
                            )
                        ]

                    sr = score_candidate_edge(
                        intent_kind=intent_kind,
                        intent_confidence=intent_confidence,
                        validation_confidence=validation_confidence,
                        source_outcome=outcome_type,
                        target_outcome=target_outcome,
                        edge_kind=edge_kind,
                        source_screen=source_screen,
                        target_screen=target_screen,
                        source_upload_order=source_upload_order,
                        target_upload_order=target_upload_order,
                        source_corpus=source_corpus,
                        target_corpus=target_corpus,
                        source_visible_texts=list(source_vis),
                        target_visible_texts=list(target.get("visible_text") or []),
                        source_screen_purpose=str(state.get("screen_purpose") or ""),
                        target_screen_purpose=str(target.get("screen_purpose") or ""),
                        source_domain=state.get("domain"),
                        target_domain=target.get("domain"),
                        source_presentation_scope=source_ps,
                        target_presentation_scope=tgt_pres,
                        uses_template_sequence=False,
                        action_steps=_serialize_steps(action_steps),
                        source_group_id=group_id,
                        source_screen_intent_id=intent_id,
                        main_action_texts=list(main_text),
                        specific_value_matched=specific_matched,
                        target_has_extracted_specific_values=bool(target_values),
                        ambiguous_selection=ambiguous_sel,
                        unresolved_selection=unresolved_sel,
                        intent_has_evidence=_intent_has_evidence(intent),
                        unordered_images_allowed=settings.UNORDERED_IMAGES_ALLOWED,
                    )

                    rf = list(sr.risk_flags)
                    edge = CandidateEdge(
                        edge_id=_generate_edge_id(run_id),
                        from_state=state_id or "",
                        to_state=target_id or "",
                        edge_kind=edge_kind,
                        scenario_role=scenario_role,
                        action_sequence=action_steps,
                        context_parameters=ctx_params,
                        source_visible_evidence=state.get("visible_text") or [],
                        target_visible_evidence=target.get("visible_text") or [],
                        confidence="medium",
                        edge_score=float(sr.value),
                        edge_score_reasons=sr.reasons,
                        edge_risk_flags=rf,
                    )
                    dumped = edge.model_dump()
                    dumped["_resolver_meta"] = {
                        "intent_kind": intent_kind,
                        "source_outcome": outcome_type,
                        "target_outcome": target_outcome,
                    }
                    candidate_edges.append(dumped)

    apply_many_compatible_targets_penalty(candidate_edges)

    filtered: List[Dict[str, Any]] = []

    for edge in candidate_edges:
        meta = edge.pop("_resolver_meta", {})
        ik = meta.get("intent_kind", "")
        ec = derive_edge_class(
            str(ik),
            str(meta.get("source_outcome", "neutral")),
            str(meta.get("target_outcome", "neutral")),
            str(edge.get("edge_kind", "")),
        )
        rf = list(edge.get("edge_risk_flags") or [])
        keep, _reason = should_keep_edge(
            int(edge.get("edge_score", 0)),
            ec,
            rf,
            prune_threshold=int(settings.CANDIDATE_EDGE_PRUNE_THRESHOLD),
            weak_threshold=int(settings.CANDIDATE_EDGE_WEAK_THRESHOLD),
            threshold_overrides=None,
            allow_weak_band=not settings.CANDIDATE_EDGE_DISABLE_WEAK_BAND,
        )
        if not keep:
            continue

        edge["confidence"] = classify_confidence(int(edge.get("edge_score", 0)), rf)
        filtered.append(edge)

    return _merge_candidate_edges(filtered)
