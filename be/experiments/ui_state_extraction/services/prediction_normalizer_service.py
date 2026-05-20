"""Convert raw JointScreenUnderstanding-shaped dict to prediction evaluation units."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
    PredActionUnit,
    PredElementUnit,
    PredExpectedStepUnit,
    PredFeedbackUnit,
    PredGroupUnit,
    PredIntentUnit,
    PredScreenUnit,
    PredictionEvaluationBundle,
)
from experiments.ui_state_extraction.services.pred_evaluation_view import (
    PredEvaluationDiagnostics,
    PredEvaluationView,
    ScreenEvaluationFields,
)
from experiments.ui_state_extraction.services.evaluation_key_service import (
    action_key,
    build_action_lookup_by_id,
    element_key,
    feedback_key,
    intent_key,
)
from experiments.ui_state_extraction.services.joint_raw_parse_helpers import (
    as_str_list,
    safe_dict,
    safe_list,
)
from experiments.ui_state_extraction.services.text_match_service import normalize_text_list
from experiments.ui_state_extraction.services.text_normalization_service import (
    normalized_join_contains,
    text_matches,
)

from app.constants.screen_intent_taxonomy import LEGACY_INTENT_KIND_MAP, normalize_action_type

_ACTION_TYPE_SET_A: frozenset[str] = frozenset({"click", "open", "close"})
_ACTION_TYPE_SET_B: frozenset[str] = frozenset(
    {"type", "select", "toggle", "upload", "drag", "scroll"},
)


def _canonical_action_type(raw: str) -> str:
    return normalize_action_type(raw)


def _canonical_intent_kind(raw: str) -> str:
    s = (raw or "").strip().lower()
    return LEGACY_INTENT_KIND_MAP.get(s, s)


_INPUT_ROLE_HINTS: frozenset[str] = frozenset({"required_input", "optional_input"})


def _anchor_from_texts(texts: list[str], *, auto_flags: list[str], kind: str, unit_id: str) -> list[str]:
    raw = [t.strip() for t in texts if t and str(t).strip()]
    anchors = normalize_text_list(raw)
    if not raw:
        if kind == "element":
            auto_flags.append(f"element_anchor_text_empty:{unit_id}")
    elif not anchors:
        auto_flags.append(f"{kind}_anchor_norm_empty:{unit_id}")
    return anchors


def _ground_type_a_pred(
    action: Mapping[str, Any],
    element_by_model_id: dict[str, dict[str, Any]],
) -> tuple[list[str], str] | None:
    texts = as_str_list(action.get("text"))
    for el in element_by_model_id.values():
        el_texts = as_str_list(el.get("text"))
        for at in texts:
            for et in el_texts:
                if text_matches(at, et):
                    eid = str(el.get("element_id", ""))
                    if not eid:
                        continue
                    anchors = [t.strip() for t in el_texts if t and str(t).strip()]
                    return (anchors if anchors else [et.strip()], eid)
    return None


def _ground_type_b_pred(
    action: Mapping[str, Any],
    action_to_group: dict[str, dict[str, Any]],
    element_by_model_id: dict[str, dict[str, Any]],
) -> tuple[list[str], str] | None:
    aid = str(action.get("action_id", ""))
    grp = action_to_group.get(aid)
    if not grp:
        return None
    texts = as_str_list(action.get("text"))
    joined = " ".join(texts)
    for eid in as_str_list(grp.get("element_ids")):
        el = element_by_model_id.get(str(eid))
        if not el:
            continue
        rh = el.get("role_hint")
        if str(rh) not in _INPUT_ROLE_HINTS:
            continue
        el_texts = as_str_list(el.get("text"))
        for et in el_texts:
            if normalized_join_contains(joined, et):
                mid = str(el.get("element_id", ""))
                if mid:
                    anchors = [t.strip() for t in el_texts if t and str(t).strip()]
                    return (anchors if anchors else [et.strip()], mid)
    return None


def build_prediction_evaluation_view(raw_model_output: dict[str, Any]) -> PredEvaluationView:
    """Multiset of evaluation keys from raw model JSON (no grounding or anchor rewriting)."""
    diag = PredEvaluationDiagnostics()
    ui = safe_dict(raw_model_output.get("ui_state"))
    si = safe_dict(raw_model_output.get("screen_intents"))

    screen_fields = ScreenEvaluationFields(
        presentation_scope=str(ui.get("presentation_scope", "unknown")),
        screen_type=str(ui.get("screen_type", "other")),
        outcome_state_type=str(ui.get("outcome_state_type", "neutral")),
    )

    element_keys: Counter = Counter()
    for el in safe_list(ui.get("visible_elements")):
        ed = safe_dict(el)
        eid = str(ed.get("element_id", ""))
        ek = element_key(ed)
        if ek is None:
            diag.skipped_empty_key_element += 1
            suffix = eid if eid else "unknown"
            diag.prediction_auto_flags.append(f"pred_element_key_missing:{suffix}")
        else:
            element_keys[ek] += 1

    action_keys: Counter = Counter()
    actions_raw = safe_list(ui.get("available_actions"))
    for ac in actions_raw:
        ad = safe_dict(ac)
        aid = str(ad.get("action_id", ""))
        ak = action_key(ad)
        if ak is None:
            diag.skipped_empty_key_action += 1
            suffix = aid if aid else "unknown"
            diag.prediction_auto_flags.append(f"pred_action_key_missing:{suffix}")
        else:
            action_keys[ak] += 1

    feedback_keys: Counter = Counter()
    for fb in safe_list(ui.get("visible_feedback")):
        fd = safe_dict(fb)
        fid = str(fd.get("feedback_id", ""))
        fk = feedback_key(fd)
        if fk is None:
            diag.skipped_empty_key_feedback += 1
            suffix = fid if fid else "unknown"
            diag.prediction_auto_flags.append(f"pred_feedback_key_missing:{suffix}")
        else:
            feedback_keys[fk] += 1

    intent_keys: Counter = Counter()
    ac_lookup = build_action_lookup_by_id(actions_raw)
    for idx, it in enumerate(safe_list(si.get("screen_behaviour_intents"))):
        intent_d = safe_dict(it)
        ik = intent_key(intent_d, ac_lookup)
        if ik is None:
            diag.skipped_empty_key_intent += 1
            diag.prediction_auto_flags.append(f"pred_intent_key_missing:{idx}")
        else:
            intent_keys[ik] += 1

    return PredEvaluationView(
        screen_fields=screen_fields,
        element_keys=element_keys,
        action_keys=action_keys,
        feedback_keys=feedback_keys,
        intent_keys=intent_keys,
        diagnostics=diag,
    )


def normalize_raw_model_output(raw_model_output: dict[str, Any]) -> PredictionEvaluationBundle:
    """Build prediction-side evaluation bundle from model JSON (no GT ids)."""
    auto_flags: list[str] = []
    ui = safe_dict(raw_model_output.get("ui_state"))
    si = safe_dict(raw_model_output.get("screen_intents"))

    screen = PredScreenUnit(
        presentation_scope=str(ui.get("presentation_scope", "unknown")),
        screen_type=str(ui.get("screen_type", "other")),
        outcome_state_type=str(ui.get("outcome_state_type", "neutral")),
        domain=str(ui.get("domain", "")),
    )

    action_to_group: dict[str, dict[str, Any]] = {}
    for g in safe_list(ui.get("interaction_groups")):
        gd = safe_dict(g)
        for aid in as_str_list(gd.get("action_ids")):
            if aid and aid not in action_to_group:
                action_to_group[aid] = gd

    element_by_model_id: dict[str, dict[str, Any]] = {}
    for el in safe_list(ui.get("visible_elements")):
        ed = safe_dict(el)
        mid = str(ed.get("element_id", ""))
        if mid:
            element_by_model_id[mid] = ed

    elements: list[PredElementUnit] = []
    for el in safe_list(ui.get("visible_elements")):
        e = safe_dict(el)
        eid = str(e.get("element_id", ""))
        texts = as_str_list(e.get("text"))
        anchors = _anchor_from_texts(texts, auto_flags=auto_flags, kind="element", unit_id=eid or "unknown")
        elements.append(
            PredElementUnit(
                pred_element_id=eid,
                anchor_texts=anchors,
                element_type=str(e.get("element_type", "other")),
                role_hint=str(e.get("role_hint")) if e.get("role_hint") is not None else None,
                visual_region=str(e.get("visual_region", "unknown")),
            )
        )

    actions: list[PredActionUnit] = []
    for ac in safe_list(ui.get("available_actions")):
        a = safe_dict(ac)
        mid = str(a.get("action_id", ""))
        texts = as_str_list(a.get("text"))
        atype = _canonical_action_type(str(a.get("action_type", "unknown")))

        anchor_texts = list(texts)
        grounded: str | None = None

        if atype in _ACTION_TYPE_SET_A:
            anchored = _ground_type_a_pred(a, element_by_model_id)
            if anchored:
                anchor_texts, grounded = anchored
        elif atype in _ACTION_TYPE_SET_B:
            anchored = _ground_type_b_pred(a, action_to_group, element_by_model_id)
            if anchored:
                anchor_texts, grounded = anchored
            else:
                auto_flags.append(f"action_grounding_not_found:{mid}")
                anchor_texts = normalize_text_list(texts)
        else:
            anchored = _ground_type_b_pred(a, action_to_group, element_by_model_id)
            if anchored:
                anchor_texts, grounded = anchored
            else:
                anchored_a = _ground_type_a_pred(a, element_by_model_id)
                if anchored_a:
                    anchor_texts, grounded = anchored_a

        actions.append(
            PredActionUnit(
                pred_action_id=mid,
                source_model_texts=list(texts),
                anchor_texts=anchor_texts if isinstance(anchor_texts, list) else list(anchor_texts),
                action_type=atype,
                action_priority=str(a.get("action_priority")) if a.get("action_priority") is not None else None,
                visual_region=str(a.get("visual_region", "unknown")),
                grounded_pred_element_id=grounded,
            )
        )

    feedback: list[PredFeedbackUnit] = []
    for fb in safe_list(ui.get("visible_feedback")):
        f = safe_dict(fb)
        fid = str(f.get("feedback_id", ""))
        texts = as_str_list(f.get("text"))
        anchors = _anchor_from_texts(texts, auto_flags=auto_flags, kind="feedback", unit_id=fid or "unknown")
        feedback.append(
            PredFeedbackUnit(
                pred_feedback_id=fid,
                anchor_texts=anchors,
                feedback_type=str(f.get("feedback_type", "unknown")),
                visual_region=str(f.get("visual_region", "unknown")),
                related_pred_element_ids=[str(x) for x in as_str_list(f.get("related_element_ids"))],
            )
        )

    groups: list[PredGroupUnit] = []
    for gr in safe_list(ui.get("interaction_groups")):
        g = safe_dict(gr)
        gid = str(g.get("group_id", ""))
        groups.append(
            PredGroupUnit(
                pred_group_id=gid,
                group_type=str(g.get("group_type", "other")),
                member_pred_element_ids=[str(x) for x in as_str_list(g.get("element_ids"))],
                member_pred_action_ids=[str(x) for x in as_str_list(g.get("action_ids"))],
                member_pred_feedback_ids=[str(x) for x in as_str_list(g.get("feedback_ids"))],
                primary_pred_action_id=str(g["primary_action_id"])
                if g.get("primary_action_id") is not None
                else None,
            )
        )

    intents: list[PredIntentUnit] = []
    for idx, it in enumerate(safe_list(si.get("screen_behaviour_intents"))):
        intent = safe_dict(it)
        evidence_ids: list[str] = []
        for eref in safe_list(intent.get("evidence_refs")):
            er = safe_dict(eref)
            evidence_ids.append(str(er.get("source_id", "")))

        templates = safe_list(intent.get("local_action_sequence_templates"))
        steps_out: list[PredExpectedStepUnit] = []
        if templates:
            t0 = safe_dict(templates[0])
            for st in safe_list(t0.get("steps")):
                sd = safe_dict(st)
                sar = sd.get("source_action_id")
                ser = sd.get("source_element_id")
                steps_out.append(
                    PredExpectedStepUnit(
                        step_type=str(sd.get("step_type", "invoke_action")),
                        source_pred_action_id=str(sar) if sar is not None else None,
                        source_pred_element_id=str(ser) if ser is not None else None,
                    )
                )

        pri = intent.get("primary_action_id")
        commit = intent.get("commit_action_id")
        intents.append(
            PredIntentUnit(
                pred_intent_index=idx,
                intent_kind=_canonical_intent_kind(str(intent.get("intent_kind", ""))),
                source_pred_group_id=str(intent.get("source_group_id", "")),
                primary_pred_action_id=str(pri) if pri is not None else None,
                commit_pred_action_id=str(commit) if commit is not None else None,
                secondary_pred_action_ids=[str(x) for x in as_str_list(intent.get("secondary_action_ids"))],
                required_pred_element_ids=[
                    str(x) for x in as_str_list(intent.get("required_input_element_ids"))
                ],
                evidence_pred_target_ids=evidence_ids,
                expected_steps=steps_out,
            )
        )

    return PredictionEvaluationBundle(
        screen=screen,
        elements=elements,
        actions=actions,
        feedback=feedback,
        groups=groups,
        intents=intents,
        auto_flags=auto_flags,
    )
