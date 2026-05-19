"""Convert raw JointScreenUnderstanding-shaped dict to prediction evaluation units."""

from __future__ import annotations

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
from experiments.ui_state_extraction.services.text_match_service import normalize_text_list
from experiments.ui_state_extraction.services.text_normalization_service import (
    normalized_join_contains,
    text_matches,
)

_ACTION_TYPE_SET_A: frozenset[str] = frozenset(
    {"click", "submit", "navigate", "open", "close", "confirm", "cancel"},
)
_ACTION_TYPE_SET_B: frozenset[str] = frozenset(
    {"type", "select", "toggle", "upload", "drag", "scroll"},
)
_INPUT_ROLE_HINTS: frozenset[str] = frozenset({"required_input", "optional_input"})


def _safe_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_list(v: Any) -> list[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return []


def _as_str_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


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
    texts = _as_str_list(action.get("text"))
    for el in element_by_model_id.values():
        el_texts = _as_str_list(el.get("text"))
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
    texts = _as_str_list(action.get("text"))
    joined = " ".join(texts)
    for eid in _as_str_list(grp.get("element_ids")):
        el = element_by_model_id.get(str(eid))
        if not el:
            continue
        rh = el.get("role_hint")
        if str(rh) not in _INPUT_ROLE_HINTS:
            continue
        el_texts = _as_str_list(el.get("text"))
        for et in el_texts:
            if normalized_join_contains(joined, et):
                mid = str(el.get("element_id", ""))
                if mid:
                    anchors = [t.strip() for t in el_texts if t and str(t).strip()]
                    return (anchors if anchors else [et.strip()], mid)
    return None


def normalize_raw_model_output(raw_model_output: dict[str, Any]) -> PredictionEvaluationBundle:
    """Build prediction-side evaluation bundle from model JSON (no GT ids)."""
    auto_flags: list[str] = []
    ui = _safe_dict(raw_model_output.get("ui_state"))
    si = _safe_dict(raw_model_output.get("screen_intents"))

    screen = PredScreenUnit(
        presentation_scope=str(ui.get("presentation_scope", "unknown")),
        screen_type=str(ui.get("screen_type", "other")),
        outcome_state_type=str(ui.get("outcome_state_type", "neutral")),
        domain=str(ui.get("domain", "")),
    )

    action_to_group: dict[str, dict[str, Any]] = {}
    for g in _safe_list(ui.get("interaction_groups")):
        gd = _safe_dict(g)
        for aid in _as_str_list(gd.get("action_ids")):
            if aid and aid not in action_to_group:
                action_to_group[aid] = gd

    element_by_model_id: dict[str, dict[str, Any]] = {}
    for el in _safe_list(ui.get("visible_elements")):
        ed = _safe_dict(el)
        mid = str(ed.get("element_id", ""))
        if mid:
            element_by_model_id[mid] = ed

    elements: list[PredElementUnit] = []
    for el in _safe_list(ui.get("visible_elements")):
        e = _safe_dict(el)
        eid = str(e.get("element_id", ""))
        texts = _as_str_list(e.get("text"))
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
    for ac in _safe_list(ui.get("available_actions")):
        a = _safe_dict(ac)
        mid = str(a.get("action_id", ""))
        texts = _as_str_list(a.get("text"))
        atype = str(a.get("action_type", "unknown"))

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
    for fb in _safe_list(ui.get("visible_feedback")):
        f = _safe_dict(fb)
        fid = str(f.get("feedback_id", ""))
        texts = _as_str_list(f.get("text"))
        anchors = _anchor_from_texts(texts, auto_flags=auto_flags, kind="feedback", unit_id=fid or "unknown")
        feedback.append(
            PredFeedbackUnit(
                pred_feedback_id=fid,
                anchor_texts=anchors,
                feedback_type=str(f.get("feedback_type", "unknown")),
                visual_region=str(f.get("visual_region", "unknown")),
                related_pred_element_ids=[str(x) for x in _as_str_list(f.get("related_element_ids"))],
            )
        )

    groups: list[PredGroupUnit] = []
    for gr in _safe_list(ui.get("interaction_groups")):
        g = _safe_dict(gr)
        gid = str(g.get("group_id", ""))
        groups.append(
            PredGroupUnit(
                pred_group_id=gid,
                group_type=str(g.get("group_type", "other")),
                member_pred_element_ids=[str(x) for x in _as_str_list(g.get("element_ids"))],
                member_pred_action_ids=[str(x) for x in _as_str_list(g.get("action_ids"))],
                member_pred_feedback_ids=[str(x) for x in _as_str_list(g.get("feedback_ids"))],
                primary_pred_action_id=str(g["primary_action_id"])
                if g.get("primary_action_id") is not None
                else None,
            )
        )

    intents: list[PredIntentUnit] = []
    for idx, it in enumerate(_safe_list(si.get("screen_behaviour_intents"))):
        intent = _safe_dict(it)
        evidence_ids: list[str] = []
        for eref in _safe_list(intent.get("evidence_refs")):
            er = _safe_dict(eref)
            evidence_ids.append(str(er.get("source_id", "")))

        templates = _safe_list(intent.get("local_action_sequence_templates"))
        steps_out: list[PredExpectedStepUnit] = []
        if templates:
            t0 = _safe_dict(templates[0])
            for st in _safe_list(t0.get("steps")):
                sd = _safe_dict(st)
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
                intent_kind=str(intent.get("intent_kind", "")),
                source_pred_group_id=str(intent.get("source_group_id", "")),
                primary_pred_action_id=str(pri) if pri is not None else None,
                commit_pred_action_id=str(commit) if commit is not None else None,
                secondary_pred_action_ids=[str(x) for x in _as_str_list(intent.get("secondary_action_ids"))],
                required_pred_element_ids=[
                    str(x) for x in _as_str_list(intent.get("required_input_element_ids"))
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
