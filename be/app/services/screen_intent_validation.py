"""Validate Phase 2 screen-intent drafts, hydrate catalog rows, derive confidences."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from app.constants.screen_intent_taxonomy import (
    ELEMENT_SCOPED_EVIDENCE_TYPES,
    INPUT_FAMILY_ELEMENT_TYPES,
    INTENT_KIND_VALUES,
    SEARCH_ACTION_HINTS,
    normalize_action_type,
)
from app.model_providers.schemas import (
    ActionSequenceStepA2,
    ActionSequenceTemplateA2,
    EvidenceRefDraftA2,
    EvidenceRefHydratedA2,
    ScreenBehaviourIntentA2,
    ScreenBehaviourIntentDraftA2,
    ScreenIntentPrimaryActionA2,
    ScreenIntentExtractionV2Result,
    SelectionOptionA2,
    SelectionOptionDraftA2,
    UnresolvedScreenGroupA2,
)

_OUTCOME_LANGUAGE = re.compile(
    r"\b("
    r"will\s+(?:successfully\s+)?(?:complete|finish|submit|redirect)|"
    r"next\s+screen|following\s+(?:step|screen)|navigate\s+to|lands?\s+on|"
    r"(?:successful|successful\s+submission)|results?\s+in\s+(?:success|failure)|"
    r"eventually\s+(?:reach|redirect)"
    r")\b",
    re.I,
)


CONF_RANK = {"high": 3, "medium": 2, "low": 1}


def merge_confidences(model_conf: str, validation_conf: str) -> str:
    r = CONF_RANK.get((model_conf or "low").lower(), 1)
    v = CONF_RANK.get((validation_conf or "low").lower(), 1)
    m = min(r, v)
    if m <= 1:
        return "low"
    if m >= 3:
        return "high"
    return "medium"


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def build_lookup_maps(state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    elements_by_id = {e["element_id"]: e for e in state.get("visible_elements") or []}
    actions_by_id = {a["action_id"]: a for a in state.get("available_actions") or []}
    feedback_by_id = {f["feedback_id"]: f for f in state.get("visible_feedback") or []}
    return elements_by_id, actions_by_id, feedback_by_id


def build_allowed_constraints(state: Dict[str, Any]) -> Dict[str, Any]:
    interaction_groups = state.get("interaction_groups") or []
    allowed_group_ids: List[str] = []
    elt_by_grp: Dict[str, List[str]] = {}
    act_by_grp: Dict[str, List[str]] = {}
    fb_by_grp: Dict[str, List[str]] = {}
    for g in interaction_groups:
        gid = g.get("group_id")
        if not gid:
            continue
        allowed_group_ids.append(gid)
        elt_by_grp[gid] = list(g.get("element_ids") or [])
        act_by_grp[gid] = list(g.get("action_ids") or [])
        fb_by_grp[gid] = list(g.get("feedback_ids") or [])
    return {
        "allowed_group_ids": allowed_group_ids,
        "allowed_element_ids_by_group": elt_by_grp,
        "allowed_action_ids_by_group": act_by_grp,
        "allowed_feedback_ids_by_group": fb_by_grp,
    }


def _hydrate_primary_action(actions_by_id: Dict[str, Any], action_id: str) -> ScreenIntentPrimaryActionA2 | None:
    act = actions_by_id.get(action_id)
    if not act:
        return None
    return ScreenIntentPrimaryActionA2(
        action_id=act.get("action_id"),
        action_type=normalize_action_type(str(act.get("action_type") or "unknown")),
        text=list(act.get("text") or []),
    )


def _resolve_option_text_from_ref(
    opt: SelectionOptionDraftA2,
    elements_by_id: Dict[str, Any],
    actions_by_id: Dict[str, Any],
) -> List[str]:
    if opt.option_ref_type == "element" and opt.option_element_id:
        el = elements_by_id.get(opt.option_element_id)
        return list((el or {}).get("text") or [])
    if opt.option_ref_type == "action" and opt.option_action_id:
        ac = actions_by_id.get(opt.option_action_id)
        return list((ac or {}).get("text") or [])
    return []


def _hydrate_evidence_ref(
    ref: EvidenceRefDraftA2,
    group: Dict[str, Any],
    elements_by_id: Dict[str, Any],
    actions_by_id: Dict[str, Any],
    feedback_by_id: Dict[str, Any],
    group_elements: Iterable[str],
    group_actions: Iterable[str],
    group_feedback: Iterable[str],
) -> Tuple[EvidenceRefHydratedA2 | None, str | None]:
    """Returns (hydrated, reject_reason_or_none)."""
    ge = frozenset(group_elements)
    ga = frozenset(group_actions)
    gf = frozenset(group_feedback)
    gid = group.get("group_id")
    etype = ref.evidence_type
    sid = ref.source_id.strip()

    if etype == "group_evidence":
        if sid != gid:
            return None, "evidence_source_not_group"
        label = group.get("group_label") or ""
        pooled: List[str] = []
        if label:
            pooled.append(label)
        for eid in group_elements:
            el = elements_by_id.get(eid)
            if el:
                pooled.extend(el.get("text") or [])
        return EvidenceRefHydratedA2(evidence_type=etype, source_id=sid, text=pooled[:8]), None

    if etype in ELEMENT_SCOPED_EVIDENCE_TYPES:
        if sid not in ge:
            return None, "invalid_element_evidence_reference"
        el = elements_by_id.get(sid)
        texts = list((el or {}).get("text") or []) if el else []
        return EvidenceRefHydratedA2(evidence_type=etype, source_id=sid, text=texts), None

    if etype == "action_text":
        if sid not in ga:
            return None, "invalid_action_evidence_reference"
        ac = actions_by_id.get(sid)
        texts = list((ac or {}).get("text") or []) if ac else []
        return EvidenceRefHydratedA2(evidence_type=etype, source_id=sid, text=texts), None

    if etype == "feedback_text":
        if sid not in gf:
            return None, "invalid_feedback_evidence_reference"
        fb = feedback_by_id.get(sid)
        texts = list((fb or {}).get("text") or []) if fb else []
        return EvidenceRefHydratedA2(evidence_type=etype, source_id=sid, text=texts), None

    return None, "unknown_evidence_type"


def _hydrate_step_text(
    source_action_id: Optional[str],
    source_element_id: Optional[str],
    actions_by_id: Dict[str, Any],
    elements_by_id: Dict[str, Any],
) -> List[str]:
    texts: List[str] = []
    if source_action_id:
        ac = actions_by_id.get(source_action_id)
        if ac:
            texts.extend(ac.get("text") or [])
    if source_element_id:
        el = elements_by_id.get(source_element_id)
        if el:
            texts.extend(el.get("text") or [])
    return texts


def _group_has_search_affordance(
    actions_by_id: Dict[str, Any],
    element_ids: Sequence[str],
    action_ids: Sequence[str],
    elements_by_id: Dict[str, Any],
) -> bool:
    for aid in action_ids:
        ac = actions_by_id.get(aid)
        if not ac:
            continue
        at = normalize_action_type(_norm(ac.get("action_type")))
        if at in SEARCH_ACTION_HINTS:
            return True
        merged = " ".join(ac.get("text") or []).lower()
        if "search" in merged:
            return True
    for eid in element_ids:
        el = elements_by_id.get(eid)
        if not el:
            continue
        merged = " ".join(el.get("text") or []).lower()
        roles = {_norm(el.get("role_hint"))}
        et = _norm(el.get("element_type"))
        if ("search" in merged) or (et == "input" and "search" in merged):
            return True
        if roles & {"navigation"} and "search" in merged:
            return True
    return False


def _group_has_filter_affordance(
    group: Mapping[str, Any],
    actions_by_id: Dict[str, Any],
    element_ids: Sequence[str],
    action_ids: Sequence[str],
    elements_by_id: Dict[str, Any],
) -> bool:
    """True when the group looks like filter/sort/narrow per prompt §4.1 ``filtering``."""
    gt = _norm(group.get("group_type"))
    if gt in ("filter", "search"):
        return True
    hints = ("filter", "sort", "refine", "narrow")
    for aid in action_ids:
        ac = actions_by_id.get(aid)
        if not ac:
            continue
        at = normalize_action_type(_norm(ac.get("action_type")))
        blob = " ".join(ac.get("text") or []).lower()
        if at in ("select", "toggle", "open", "type", "click") and any(h in blob for h in hints):
            return True
    for eid in element_ids:
        el = elements_by_id.get(eid)
        if not el:
            continue
        blob = " ".join(el.get("text") or []).lower()
        if any(h in blob for h in hints):
            return True
    return False


def _group_feedback_ack_actions(
    actions_by_id: Dict[str, Any],
    action_ids: Sequence[str],
) -> List[str]:
    ack = []
    for aid in action_ids:
        ac = actions_by_id.get(aid)
        if not ac:
            continue
        blob = " ".join(ac.get("text") or []).lower()
        if any(tok in blob for tok in ("ok", "okay", "dismiss", "got it", "close")):
            ack.append(aid)
    return ack


@dataclass
class ProcessingStats:
    accepted: int = 0
    rejected: int = 0
    intent_kind_counts: Dict[str, int] = field(default_factory=dict)
    unresolved_reason_counts: Dict[str, int] = field(default_factory=dict)
    downgrade_count: int = 0


def process_screen_intents_for_state(
    state: Dict[str, Any],
    llm_payload: ScreenIntentExtractionV2Result,
    id_factory: Callable[[], str] | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], ProcessingStats]:
    """
    Returns (validated_catalog_dicts, merged_unresolved_dicts, per_state_validation_summary, stats).
    """
    if id_factory is None:
        id_factory = lambda: f"sbi_{uuid.uuid4().hex[:12]}"

    elements_by_id, actions_by_id, feedback_by_id = build_lookup_maps(state)
    state_id = state["state_id"]
    groups_by_id = {g["group_id"]: g for g in (state.get("interaction_groups") or []) if g.get("group_id")}

    unresolved_out: List[Dict[str, Any]] = []

    # LLM-produced unresolved rows
    for u in llm_payload.unresolved_screen_groups:
        unresolved_out.append(u.model_dump() | {"source_state_id": state_id})

    catalog: List[Dict[str, Any]] = []
    stats = ProcessingStats()
    validations: List[Dict[str, Any]] = []

    for draft in llm_payload.screen_behaviour_intents:
        gid = draft.source_group_id
        vr = validate_and_hydrate_intent(
            state_id=state_id,
            draft=draft,
            group=groups_by_id.get(gid),
            elements_by_id=elements_by_id,
            actions_by_id=actions_by_id,
            feedback_by_id=feedback_by_id,
            id_factory=id_factory,
        )

        validations.append({"source_group_id": gid, **vr.detail})

        if vr.rejected and vr.reject_unresolved:
            unresolved_out.append(
                {
                    "group_id": vr.reject_group_id or gid,
                    "reason_code": vr.reject_unresolved.reason_code,
                    "details": vr.reject_unresolved.details,
                    "source_state_id": state_id,
                }
            )
            stats.rejected += 1
            code = vr.reject_unresolved.reason_code
            stats.unresolved_reason_counts[code] = stats.unresolved_reason_counts.get(code, 0) + 1
            continue

        if vr.catalog_intent:
            cid = vr.catalog_intent.intent_kind
            stats.intent_kind_counts[cid] = stats.intent_kind_counts.get(cid, 0) + 1
            row = vr.catalog_intent.model_dump()
            row["_validation_detail"] = vr.detail
            catalog.append(row)
            stats.accepted += 1
            if vr.validation_confidence != "high" or vr.downgraded_from_ids:
                stats.downgrade_count += 1

    summary = {
        "state_id": state_id,
        "validated_intents": len(catalog),
        "rejected_intents": stats.rejected,
        "intent_kind_counts": dict(stats.intent_kind_counts),
        "unresolved_reason_counts": dict(stats.unresolved_reason_counts),
        "per_intent_reports": validations,
    }
    return catalog, unresolved_out, summary, stats


@dataclass
class ValidationOutcome:
    catalog_intent: ScreenBehaviourIntentA2 | None
    rejected: bool
    reject_unresolved: UnresolvedScreenGroupA2 | None
    reject_group_id: Optional[str]
    validation_confidence: str
    detail: Dict[str, Any]
    downgraded_from_ids: bool = False


def validate_and_hydrate_intent(
    *,
    state_id: str,
    draft: ScreenBehaviourIntentDraftA2,
    group: Optional[Dict[str, Any]],
    elements_by_id: Dict[str, Any],
    actions_by_id: Dict[str, Any],
    feedback_by_id: Dict[str, Any],
    id_factory: Callable[[], str],
) -> ValidationOutcome:
    gid = draft.source_group_id
    trace: Dict[str, Any] = {"issues": []}

    def add_issue(level: str, code: str, msg: str) -> None:
        trace["issues"].append({"level": level, "code": code, "message": msg})

    if group is None:
        add_issue("severe", "invalid_group", gid)
        return ValidationOutcome(
            catalog_intent=None,
            rejected=True,
            reject_unresolved=UnresolvedScreenGroupA2(
                group_id=gid,
                reason_code="invalid_source_group_id",
                details="source_group_id not present in state's interaction_groups",
            ),
            reject_group_id=gid,
            validation_confidence="low",
            detail=trace,
        )

    elt_ids_set = frozenset(group.get("element_ids") or ())
    action_ids_set = frozenset(group.get("action_ids") or ())
    feedback_ids_set = frozenset(group.get("feedback_ids") or ())
    gid_str = group.get("group_id") or gid

    if draft.intent_kind not in INTENT_KIND_VALUES:
        add_issue("severe", "bad_kind", draft.intent_kind)
        return ValidationOutcome(
            None,
            True,
            UnresolvedScreenGroupA2(
                group_id=gid_str,
                reason_code="unsupported_intent_kind",
                details=f"intent_kind={draft.intent_kind!r}",
            ),
            gid_str,
            "low",
            trace,
        )

    if _OUTCOME_LANGUAGE.search(draft.local_user_goal) or _OUTCOME_LANGUAGE.search(draft.intent_name):
        add_issue("severe", "outcome_prediction", draft.intent_name)
        return ValidationOutcome(
            None,
            True,
            UnresolvedScreenGroupA2(
                group_id=gid_str,
                reason_code="outcome_prediction_detected",
                details="local_user_goal/intent_name contains cross-state/outcome wording",
            ),
            gid_str,
            "low",
            trace,
        )

    validation_conf = "high"
    downgraded = False

    def need_medium(msg: str) -> None:
        nonlocal validation_conf, downgraded
        if validation_conf == "high":
            validation_conf = "medium"
        add_issue("medium", "soft", msg)
        downgraded = True

    def hydrate_action_optional(aid: Optional[str]) -> ScreenIntentPrimaryActionA2 | None:
        if not aid:
            return None
        h = _hydrate_primary_action(actions_by_id, aid)
        return h

    if draft.primary_action_id and draft.primary_action_id not in action_ids_set:
        return ValidationOutcome(
            None,
            True,
            UnresolvedScreenGroupA2(
                group_id=gid_str,
                reason_code="invalid_action_reference",
                details=f"primary_action_id {draft.primary_action_id} not in group",
            ),
            gid_str,
            "low",
            trace,
        )
    if draft.commit_action_id and draft.commit_action_id not in action_ids_set:
        return ValidationOutcome(
            None,
            True,
            UnresolvedScreenGroupA2(
                group_id=gid_str,
                reason_code="invalid_action_reference",
                details=f"commit_action_id {draft.commit_action_id} not in group",
            ),
            gid_str,
            "low",
            trace,
        )

    kept_secondaries: List[str] = []
    for sid in draft.secondary_action_ids:
        if sid in action_ids_set:
            kept_secondaries.append(sid)
        else:
            need_medium(f"Dropped secondary_action_id {sid} missing from group")
    secondary_hydrated = [h for h in (hydrate_action_optional(a) for a in kept_secondaries) if h]

    primary_h = hydrate_action_optional(draft.primary_action_id)
    commit_h = hydrate_action_optional(draft.commit_action_id)

    if draft.intent_kind == "submission" and commit_h is None:
        add_issue("severe", "submission_without_commit", "")
        return ValidationOutcome(
            None,
            True,
            UnresolvedScreenGroupA2(
                group_id=gid_str,
                reason_code="conflicting_action_roles",
                details="submission requires commit_action_id present in group",
            ),
            gid_str,
            "low",
            trace,
        )

    if draft.intent_kind == "confirmation" and commit_h is None:
        add_issue("severe", "confirmation_without_commit", "")
        return ValidationOutcome(
            None,
            True,
            UnresolvedScreenGroupA2(
                group_id=gid_str,
                reason_code="conflicting_action_roles",
                details="confirmation requires commit_action_id present in group",
            ),
            gid_str,
            "low",
            trace,
        )

    if draft.intent_kind == "creation" and commit_h is None and primary_h is None:
        add_issue("severe", "creation_without_action", "")
        return ValidationOutcome(
            None,
            True,
            UnresolvedScreenGroupA2(
                group_id=gid_str,
                reason_code="conflicting_action_roles",
                details="creation requires primary_action_id and/or commit_action_id in group",
            ),
            gid_str,
            "low",
            trace,
        )

    if draft.intent_kind == "informational":
        if commit_h is not None:
            add_issue("severe", "informational_commit", "")
            return ValidationOutcome(
                None,
                True,
                UnresolvedScreenGroupA2(
                    group_id=gid_str,
                    reason_code="conflicting_action_roles",
                    details="informational must not declare commit_action_id",
                ),
                gid_str,
                "low",
                trace,
            )
        # primary allowed only for benign navigation affordances inside group
        if primary_h:
            pt = normalize_action_type(_norm(primary_h.action_type))
            if pt not in ("open", "click", "unknown"):
                return ValidationOutcome(
                    None,
                    True,
                    UnresolvedScreenGroupA2(
                        group_id=gid_str,
                        reason_code="conflicting_action_roles",
                        details=f"informational disallows actionable primary ({primary_h.action_type})",
                    ),
                    gid_str,
                    "low",
                    trace,
                )

    hydrated_options: List[SelectionOptionA2] = []
    for od in draft.selection_options:
        if od.option_ref_type == "element":
            if not od.option_element_id or od.option_action_id:
                return ValidationOutcome(
                    None,
                    True,
                    UnresolvedScreenGroupA2(
                        group_id=gid_str,
                        reason_code="invalid_element_reference",
                        details="option_ref_type element expects option_element_id only",
                    ),
                    gid_str,
                    "low",
                    trace,
                )
            if od.option_element_id not in elt_ids_set:
                return ValidationOutcome(
                    None,
                    True,
                    UnresolvedScreenGroupA2(
                        group_id=gid_str,
                        reason_code="invalid_element_reference",
                        details=f"option_element_id {od.option_element_id}",
                    ),
                    gid_str,
                    "low",
                    trace,
                )
        else:
            if not od.option_action_id or od.option_element_id:
                return ValidationOutcome(
                    None,
                    True,
                    UnresolvedScreenGroupA2(
                        group_id=gid_str,
                        reason_code="invalid_action_reference",
                        details="option_ref_type action expects option_action_id only",
                    ),
                    gid_str,
                    "low",
                    trace,
                )
            if od.option_action_id not in action_ids_set:
                return ValidationOutcome(
                    None,
                    True,
                    UnresolvedScreenGroupA2(
                        group_id=gid_str,
                        reason_code="invalid_action_reference",
                        details=f"option_action_id {od.option_action_id}",
                    ),
                    gid_str,
                    "low",
                    trace,
                )

        hydrated_options.append(
            SelectionOptionA2(
                option_ref_type=od.option_ref_type,
                option_element_id=od.option_element_id,
                option_action_id=od.option_action_id,
                option_text=_resolve_option_text_from_ref(od, elements_by_id, actions_by_id),
                visible_status=od.visible_status,
            )
        )

    required_kept = []
    for eid in draft.required_input_element_ids:
        el = elements_by_id.get(eid)
        if eid not in elt_ids_set:
            return ValidationOutcome(
                None,
                True,
                UnresolvedScreenGroupA2(
                    group_id=gid_str,
                    reason_code="invalid_element_reference",
                    details=f"required_input_element_id {eid} not in group",
                ),
                gid_str,
                "low",
                trace,
            )
        etype = _norm(el.get("element_type") if el else None)
        if etype not in INPUT_FAMILY_ELEMENT_TYPES and el:
            need_medium(f"Element {eid} type {etype} not typical input-family")
        required_kept.append(eid)

    if draft.intent_kind == "data_entry" and not required_kept:
        empties_have_input = any(
            (_norm(elements_by_id.get(eid).get("element_type")) in INPUT_FAMILY_ELEMENT_TYPES)
            for eid in elt_ids_set
            if elements_by_id.get(eid)
        )
        if empties_have_input:
            need_medium("data_entry without required_input_element_ids while inputs exist")

    hydrated_evidence: List[EvidenceRefHydratedA2] = []
    for er in draft.evidence_refs:
        h, rej = _hydrate_evidence_ref(
            er,
            group,
            elements_by_id,
            actions_by_id,
            feedback_by_id,
            elt_ids_set,
            action_ids_set,
            feedback_ids_set,
        )
        if rej or h is None:
            return ValidationOutcome(
                None,
                True,
                UnresolvedScreenGroupA2(
                    group_id=gid_str,
                    reason_code="no_grounded_evidence",
                    details=f"evidence ref {er.source_id} ({rej or 'reject'})",
                ),
                gid_str,
                "low",
                trace,
            )
        hydrated_evidence.append(h)

    if not hydrated_evidence:
        need_medium("No evidence_refs supplied — intent confidence capped")

    if draft.intent_kind == "search":
        allowed = _group_has_search_affordance(actions_by_id, list(elt_ids_set), list(action_ids_set), elements_by_id)
        if not allowed:
            return ValidationOutcome(
                None,
                True,
                UnresolvedScreenGroupA2(
                    group_id=gid_str,
                    reason_code="conflicting_action_roles",
                    details="search intent_kind requires explicit search affordance/action in group",
                ),
                gid_str,
                "low",
                trace,
            )

    if draft.intent_kind == "filtering":
        allowed = _group_has_filter_affordance(
            group, actions_by_id, list(elt_ids_set), list(action_ids_set), elements_by_id
        )
        if not allowed:
            return ValidationOutcome(
                None,
                True,
                UnresolvedScreenGroupA2(
                    group_id=gid_str,
                    reason_code="conflicting_action_roles",
                    details="filtering intent_kind requires filter/sort/refine affordance or filter/search group_type",
                ),
                gid_str,
                "low",
                trace,
            )

    if draft.intent_kind == "feedback_acknowledgement":
        if not feedback_ids_set:
            return ValidationOutcome(
                None,
                True,
                UnresolvedScreenGroupA2(
                    group_id=gid_str,
                    reason_code="no_actionable_control",
                    details="feedback_acknowledgement requires visible_feedback in group",
                ),
                gid_str,
                "low",
                trace,
            )
        if not _group_feedback_ack_actions(actions_by_id, list(action_ids_set)):
            return ValidationOutcome(
                None,
                True,
                UnresolvedScreenGroupA2(
                    group_id=gid_str,
                    reason_code="no_actionable_control",
                    details="feedback_acknowledgement requires explicit acknowledge/dismiss action",
                ),
                gid_str,
                "low",
                trace,
            )

    tmpl_hydrated: List[ActionSequenceTemplateA2] = []
    for tmpl in draft.local_action_sequence_templates:
        steps_h: List[ActionSequenceStepA2] = []
        for step in tmpl.steps:
            if step.source_action_id and step.source_action_id not in action_ids_set:
                return ValidationOutcome(
                    None,
                    True,
                    UnresolvedScreenGroupA2(
                        group_id=gid_str,
                        reason_code="invalid_action_reference",
                        details=f"sequence references action outside group ({step.source_action_id})",
                    ),
                    gid_str,
                    "low",
                    trace,
                )
            if step.source_element_id and step.source_element_id not in elt_ids_set:
                return ValidationOutcome(
                    None,
                    True,
                    UnresolvedScreenGroupA2(
                        group_id=gid_str,
                        reason_code="invalid_element_reference",
                        details=f"sequence references element outside group ({step.source_element_id})",
                    ),
                    gid_str,
                    "low",
                    trace,
                )
            st_ob = ActionSequenceStepA2(
                step_type=step.step_type,
                source_action_id=step.source_action_id,
                source_element_id=step.source_element_id,
                text=_hydrate_step_text(
                    step.source_action_id,
                    step.source_element_id,
                    actions_by_id,
                    elements_by_id,
                ),
            )
            steps_h.append(st_ob)

        tmpl_hydrated.append(
            ActionSequenceTemplateA2(sequence_name=tmpl.sequence_name, steps=steps_h, outcome_prediction_allowed=False)
        )

    evidence_plain = []
    for h in hydrated_evidence:
        tag = h.evidence_type
        snippet = " ".join(h.text).strip()
        evidence_plain.append(f"[{tag}] {h.source_id} {snippet}"[:500])

    if not hydrated_evidence and validation_conf == "high":
        validation_conf = "medium"

    final_conf = merge_confidences(draft.model_confidence, validation_conf)

    intent = ScreenBehaviourIntentA2(
        screen_intent_id=id_factory(),
        source_state_id=state_id,
        source_group_id=gid_str,
        intent_kind=draft.intent_kind,
        intent_name=draft.intent_name,
        local_user_goal=draft.local_user_goal,
        primary_action=primary_h,
        selection_options=hydrated_options,
        commit_action=commit_h,
        secondary_actions=secondary_hydrated,
        local_action_sequence_templates=tmpl_hydrated,
        required_input_element_ids=list(required_kept),
        evidence_refs=hydrated_evidence,
        evidence=evidence_plain,
        model_confidence=draft.model_confidence,
        validation_confidence=validation_conf,
        confidence=final_conf,
    )
    trace["validation_confidence"] = validation_conf
    trace["final_confidence"] = final_conf
    trace["draft_snapshot"] = draft.model_dump(mode="python")
    return ValidationOutcome(intent, False, None, None, validation_conf, trace, downgraded)
