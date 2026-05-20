"""Convert module 1 raw wrapper + JointScreenUnderstanding-shaped dict to temp ground truth."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from app.model_providers.schemas import JointScreenUnderstandingResult

from experiments.ui_state_extraction import config
from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
)
from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
    ActionRecord,
    AnnotationMeta,
    ConversionReport,
    DebugIdMaps,
    ElementRecord,
    ExpectedStepRecord,
    FeedbackRecord,
    GroupRecord,
    ImageMetaInTempGt,
    InvalidReferenceRecord,
    ScreenBlock,
    ScreenIntentRecord,
    TempGroundTruthDocument,
    UnresolvedGroupRecord,
)
from experiments.ui_state_extraction.services.control_label_first_heuristics import (
    control_label_first_flags_for_element,
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
from experiments.ui_state_extraction.services.text_normalization_service import (
    normalized_join_contains,
    normalize_for_match,
    text_matches,
)
from experiments.ui_state_extraction.services.validation_report_service import (
    compute_review_priority,
    sync_conversion_counts,
)

_ACTION_TYPE_SET_A: frozenset[str] = frozenset({"click", "open", "close"})
_ACTION_TYPE_SET_B: frozenset[str] = frozenset(
    {"type", "select", "toggle", "upload", "drag", "scroll"},
)
_LEGACY_ACTION_TYPES: frozenset[str] = frozenset({"submit", "navigate", "confirm", "cancel"})


def _canonical_action_type(raw: str) -> str:
    at = (raw or "unknown").strip().lower()
    if at in _LEGACY_ACTION_TYPES:
        return "click"
    return at
_INPUT_ROLE_HINTS: frozenset[str] = frozenset({"required_input", "optional_input"})


def _gt_el(i: int) -> str:
    return f"gt_el_{i:03d}"


def _gt_ac(i: int) -> str:
    return f"gt_ac_{i:03d}"


def _gt_fb(i: int) -> str:
    return f"gt_fb_{i:03d}"


def _gt_ig(i: int) -> str:
    return f"gt_ig_{i:03d}"


def _gt_intent(i: int) -> str:
    return f"gt_intent_{i:03d}"


def _gt_unresolved(i: int) -> str:
    return f"gt_unresolved_{i:03d}"


def _anchor_texts_from_model(texts: list[str], *, report: ConversionReport, kind: str, gt_id: str) -> list[str]:
    out = [t.strip() for t in texts if t and str(t).strip()]
    if not out:
        if kind == "element":
            report.auto_flags.append(f"element_anchor_text_empty:{gt_id}")
        elif kind == "feedback":
            report.auto_flags.append(f"feedback_anchor_text_empty:{gt_id}")
        return []
    if all(not normalize_for_match(t) for t in out):
        report.auto_flags.append(
            f"element_anchor_text_empty:{gt_id}" if kind == "element" else f"{kind}_anchor_norm_empty:{gt_id}"
        )
    return out


def _apply_evaluation_key_flags(
    report: ConversionReport,
    *,
    elements: list[ElementRecord],
    actions: list[ActionRecord],
    feedback: list[FeedbackRecord],
    intents: list[ScreenIntentRecord],
) -> None:
    for el in elements:
        if element_key(el) is None:
            report.auto_flags.append(f"element_key_missing:{el.gt_element_id}")
    for ac in actions:
        if action_key(ac) is None:
            report.auto_flags.append(f"action_key_missing:{ac.gt_action_id}")
    for fb in feedback:
        if feedback_key(fb) is None:
            report.auto_flags.append(f"feedback_key_missing:{fb.gt_feedback_id}")
    ac_lut = build_action_lookup_by_id(actions)
    for it in intents:
        if intent_key(it, ac_lut) is None:
            report.auto_flags.append(f"intent_key_missing:{it.gt_intent_id}")


def _apply_control_label_first_flags(
    report: ConversionReport,
    visible_elements_raw: Any,
) -> None:
    for idx, el in enumerate(safe_list(visible_elements_raw), start=1):
        e = safe_dict(el)
        gid = _gt_el(idx)
        texts = as_str_list(e.get("text"))
        et = str(e.get("element_type", "other"))
        rh = e.get("role_hint")
        for flag in control_label_first_flags_for_element(
            gid,
            texts,
            element_type=et,
            role_hint=rh,
        ):
            report.auto_flags.append(flag)


def build_temp_ground_truth_from_raw(
    doc: ExperimentRawOutputDocument,
    *,
    source_raw_output_path: str,
    validate_joint_schema: bool = True,
    include_debug_id_maps: bool | None = None,
) -> TempGroundTruthDocument:
    """Build temp GT from a module-1 wrapper. Assumes raw_model_output is present."""
    include_debug = (
        include_debug_id_maps if include_debug_id_maps is not None else config.INCLUDE_DEBUG_ID_MAPS
    )
    raw_out = doc.raw_model_output
    if raw_out is None:
        raise ValueError("raw_model_output is None")

    if validate_joint_schema:
        JointScreenUnderstandingResult.model_validate(raw_out)

    ui = safe_dict(raw_out.get("ui_state"))
    si = safe_dict(raw_out.get("screen_intents"))

    report = ConversionReport(status="converted", warnings=[], invalid_references=[], auto_flags=[])

    ann = AnnotationMeta(
        source_raw_output_path=source_raw_output_path,
        review_priority="low",
    )
    img = ImageMetaInTempGt(
        image_id=doc.image.image_id,
        source_path=doc.image.source_path,
        relative_path=doc.image.relative_path,
        filename=doc.image.filename or "",
    )
    screen = ScreenBlock(
        presentation_scope=str(ui.get("presentation_scope", "unknown")),
        screen_type=str(ui.get("screen_type", "other")),
        outcome_state_type=str(ui.get("outcome_state_type", "neutral")),
        domain=str(ui.get("domain", "")),
    )

    model_el_to_gt: dict[str, str] = {}
    model_ac_to_gt: dict[str, str] = {}
    model_fb_to_gt: dict[str, str] = {}
    model_ig_to_gt: dict[str, str] = {}

    elements_out: list[ElementRecord] = []
    for idx, el in enumerate(safe_list(ui.get("visible_elements")), start=1):
        e = safe_dict(el)
        mid = str(e.get("element_id", ""))
        gid = _gt_el(idx)
        if mid:
            model_el_to_gt[mid] = gid
        texts = as_str_list(e.get("text"))
        anchors = _anchor_texts_from_model(texts, report=report, kind="element", gt_id=gid)
        elements_out.append(
            ElementRecord(
                gt_element_id=gid,
                source_model_element_id=mid,
                anchor_texts=anchors,
                element_type=str(e.get("element_type", "other")),
                role_hint=e.get("role_hint"),
                visual_region=str(e.get("visual_region", "unknown")),
            )
        )

    # group -> action lookup (first group wins if overlap; flag multi membership separately)
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

    actions_out: list[ActionRecord] = []
    for idx, ac in enumerate(safe_list(ui.get("available_actions")), start=1):
        a = safe_dict(ac)
        mid = str(a.get("action_id", ""))
        gid = _gt_ac(idx)
        if mid:
            model_ac_to_gt[mid] = gid
        texts = as_str_list(a.get("text"))
        atype = _canonical_action_type(str(a.get("action_type", "unknown")))

        anchor_texts: list[str] = list(texts)
        grounded: str | None = None

        if atype in _ACTION_TYPE_SET_A:
            anchored = _ground_type_a(a, element_by_model_id, model_el_to_gt)
            if anchored:
                anchor_texts, grounded = anchored
        elif atype in _ACTION_TYPE_SET_B:
            anchored = _ground_type_b(a, action_to_group, element_by_model_id, model_el_to_gt)
            if anchored:
                anchor_texts, grounded = anchored
            else:
                report.auto_flags.append(f"action_grounding_not_found:{gid}")
        else:
            anchored = _ground_type_b(a, action_to_group, element_by_model_id, model_el_to_gt)
            if anchored:
                anchor_texts, grounded = anchored
            else:
                anchored_a = _ground_type_a(a, element_by_model_id, model_el_to_gt)
                if anchored_a:
                    anchor_texts, grounded = anchored_a
                report.warnings.append(f"unknown_action_type_heuristic:{gid}:{atype}")

        actions_out.append(
            ActionRecord(
                gt_action_id=gid,
                source_model_action_id=mid,
                anchor_texts=anchor_texts,
                source_model_texts=list(texts),
                action_type=atype,
                action_priority=a.get("action_priority"),
                visual_region=str(a.get("visual_region", "unknown")),
                grounded_element_id=grounded,
            )
        )

    feedback_out: list[FeedbackRecord] = []
    for idx, fb in enumerate(safe_list(ui.get("visible_feedback")), start=1):
        f = safe_dict(fb)
        mid = str(f.get("feedback_id", ""))
        gid = _gt_fb(idx)
        if mid:
            model_fb_to_gt[mid] = gid
        texts = as_str_list(f.get("text"))
        rel_in = as_str_list(f.get("related_element_ids"))
        rel_gt: list[str] = []
        for rid in rel_in:
            gtid = model_el_to_gt.get(rid)
            if gtid:
                rel_gt.append(gtid)
            else:
                report.invalid_references.append(
                    InvalidReferenceRecord(
                        field="feedback.related_element_ids",
                        source_id=rid,
                        reason="element id not found",
                    )
                )
        feedback_out.append(
            FeedbackRecord(
                gt_feedback_id=gid,
                source_model_feedback_id=mid,
                anchor_texts=_anchor_texts_from_model(texts, report=report, kind="feedback", gt_id=gid),
                feedback_type=str(f.get("feedback_type", "unknown")),
                visual_region=str(f.get("visual_region", "unknown")),
                related_element_ids=rel_gt,
            )
        )

    groups_out: list[GroupRecord] = []
    for idx, gr in enumerate(safe_list(ui.get("interaction_groups")), start=1):
        g = safe_dict(gr)
        mid = str(g.get("group_id", ""))
        ggid = _gt_ig(idx)
        if mid:
            model_ig_to_gt[mid] = ggid

        def _map_el(rid: str) -> str | None:
            return model_el_to_gt.get(rid)

        def _map_ac(rid: str) -> str | None:
            return model_ac_to_gt.get(rid)

        def _map_fb(rid: str) -> str | None:
            return model_fb_to_gt.get(rid)

        mem_el = [_map_el(x) for x in as_str_list(g.get("element_ids"))]
        mem_ac = [_map_ac(x) for x in as_str_list(g.get("action_ids"))]
        mem_fb = [_map_fb(x) for x in as_str_list(g.get("feedback_ids"))]

        for i, raw_id in enumerate(as_str_list(g.get("element_ids"))):
            if mem_el[i] is None:
                report.auto_flags.append(f"group_invalid_element_ref:{ggid}:{raw_id}")
                report.invalid_references.append(
                    InvalidReferenceRecord(
                        field=f"interaction_groups[{mid}].element_ids",
                        source_id=raw_id,
                        reason="element id not found",
                    )
                )
        for i, raw_id in enumerate(as_str_list(g.get("action_ids"))):
            if mem_ac[i] is None:
                report.auto_flags.append(f"group_invalid_action_ref:{ggid}:{raw_id}")
                report.invalid_references.append(
                    InvalidReferenceRecord(
                        field=f"interaction_groups[{mid}].action_ids",
                        source_id=raw_id,
                        reason="action id not found",
                    )
                )
        for i, raw_id in enumerate(as_str_list(g.get("feedback_ids"))):
            if mem_fb[i] is None:
                report.auto_flags.append(f"group_invalid_feedback_ref:{ggid}:{raw_id}")
                report.invalid_references.append(
                    InvalidReferenceRecord(
                        field=f"interaction_groups[{mid}].feedback_ids",
                        source_id=raw_id,
                        reason="feedback id not found",
                    )
                )

        mem_el_f = [x for x in mem_el if x is not None]
        mem_ac_f = [x for x in mem_ac if x is not None]
        mem_fb_f = [x for x in mem_fb if x is not None]

        prim_raw = g.get("primary_action_id")
        prim_gt = model_ac_to_gt.get(str(prim_raw)) if prim_raw is not None else None
        if prim_raw and prim_gt is None:
            report.invalid_references.append(
                InvalidReferenceRecord(
                    field=f"interaction_groups[{mid}].primary_action_id",
                    source_id=str(prim_raw),
                    reason="action id not found",
                )
            )
        elif prim_gt and prim_gt not in mem_ac_f:
            report.auto_flags.append("group_primary_action_not_in_group")
            report.invalid_references.append(
                InvalidReferenceRecord(
                    field=f"interaction_groups[{mid}].primary_action_id",
                    source_id=str(prim_raw),
                    reason="primary action not in member_action_ids",
                )
            )

        groups_out.append(
            GroupRecord(
                gt_group_id=ggid,
                source_model_group_id=mid,
                group_type=str(g.get("group_type", "other")),
                member_element_ids=mem_el_f,
                member_action_ids=mem_ac_f,
                member_feedback_ids=mem_fb_f,
                primary_action_id=prim_gt,
            )
        )

    _validate_group_membership(
        ui,
        model_el_to_gt,
        model_ac_to_gt,
        model_fb_to_gt,
        report,
    )

    intents_out: list[ScreenIntentRecord] = []
    for idx, it in enumerate(safe_list(si.get("screen_behaviour_intents")), start=1):
        intent = safe_dict(it)
        iid = _gt_intent(idx)
        src_g = str(intent.get("source_group_id", ""))
        gt_g = model_ig_to_gt.get(src_g)
        if not gt_g:
            report.invalid_references.append(
                InvalidReferenceRecord(
                    field=f"screen_behaviour_intents[{idx - 1}].source_group_id",
                    source_id=src_g,
                    reason="group id not found",
                )
            )
            gt_g = ""

        def _ac_gt(r: Any) -> str | None:
            if r is None:
                return None
            s = str(r)
            gta = model_ac_to_gt.get(s)
            if not gta:
                report.invalid_references.append(
                    InvalidReferenceRecord(
                        field=f"screen_intents.{iid}.action",
                        source_id=s,
                        reason="action id not found",
                    )
                )
            return gta

        pri = _ac_gt(intent.get("primary_action_id"))
        commit = _ac_gt(intent.get("commit_action_id"))
        sec_raw = as_str_list(intent.get("secondary_action_ids"))
        sec_gt = []
        for sr in sec_raw:
            x = _ac_gt(sr)
            if x:
                sec_gt.append(x)

        req_raw = as_str_list(intent.get("required_input_element_ids"))
        req_gt: list[str] = []
        for rr in req_raw:
            ge = model_el_to_gt.get(rr)
            if ge:
                req_gt.append(ge)
            else:
                report.invalid_references.append(
                    InvalidReferenceRecord(
                        field=f"screen_intents.{iid}.required_input_element_ids",
                        source_id=rr,
                        reason="element id not found",
                    )
                )

        evidence_targets: list[str] = []
        for eref in safe_list(intent.get("evidence_refs")):
            er = safe_dict(eref)
            et = str(er.get("evidence_type", ""))
            sid = str(er.get("source_id", ""))
            mapped = _map_evidence_ref(et, sid, model_el_to_gt, model_ac_to_gt, model_fb_to_gt, model_ig_to_gt)
            if mapped:
                evidence_targets.append(mapped)
            elif et == "non_text_label":
                report.auto_flags.append(f"non_text_label_skipped:{iid}")
            else:
                report.auto_flags.append(f"evidence_ref_invalid:{iid}:{et}:{sid}")
                report.invalid_references.append(
                    InvalidReferenceRecord(
                        field=f"screen_intents.{iid}.evidence_refs",
                        source_id=sid,
                        reason=f"could not map evidence_type={et}",
                    )
                )

        templates = safe_list(intent.get("local_action_sequence_templates"))
        steps_out: list[ExpectedStepRecord] = []
        if len(templates) > 1:
            report.auto_flags.append(f"multiple_sequence_templates_review_needed:{iid}")
        if templates:
            t0 = safe_dict(templates[0])
            if t0.get("outcome_prediction_allowed") is not False:
                report.auto_flags.append("outcome_prediction_allowed_not_false")
            for st in safe_list(t0.get("steps")):
                sd = safe_dict(st)
                sar = sd.get("source_action_id")
                ser = sd.get("source_element_id")
                steps_out.append(
                    ExpectedStepRecord(
                        step_type=str(sd.get("step_type", "invoke_action")),
                        source_action_id=model_ac_to_gt.get(str(sar)) if sar is not None else None,
                        source_element_id=model_el_to_gt.get(str(ser)) if ser is not None else None,
                    )
                )
                if sar and steps_out[-1].source_action_id is None:
                    report.invalid_references.append(
                        InvalidReferenceRecord(
                            field=f"{iid}.expected_steps.action",
                            source_id=str(sar),
                            reason="action id not found",
                        )
                    )
                if ser and steps_out[-1].source_element_id is None:
                    report.invalid_references.append(
                        InvalidReferenceRecord(
                            field=f"{iid}.expected_steps.element",
                            source_id=str(ser),
                            reason="element id not found",
                        )
                    )

        intents_out.append(
            ScreenIntentRecord(
                gt_intent_id=iid,
                source_model_index=idx - 1,
                intent_kind=str(intent.get("intent_kind", "")),
                source_group_id=gt_g,
                primary_action_id=pri,
                commit_action_id=commit,
                secondary_action_ids=sec_gt,
                required_input_element_ids=req_gt,
                evidence_target_ids=evidence_targets,
                expected_steps=steps_out,
            )
        )

    unresolved_out: list[UnresolvedGroupRecord] = []
    for idx, ug in enumerate(safe_list(si.get("unresolved_screen_groups")), start=1):
        u = safe_dict(ug)
        raw_gid = str(u.get("group_id", ""))
        gtg = model_ig_to_gt.get(raw_gid, "")
        unresolved_out.append(
            UnresolvedGroupRecord(
                gt_unresolved_id=_gt_unresolved(idx),
                source_model_group_id=raw_gid,
                group_id=gtg,
                reason_code=str(u.get("reason_code", "")),
            )
        )

    _apply_evaluation_key_flags(
        report,
        elements=elements_out,
        actions=actions_out,
        feedback=feedback_out,
        intents=intents_out,
    )
    _apply_control_label_first_flags(report, ui.get("visible_elements"))

    if include_debug:
        report.debug_id_maps = DebugIdMaps(
            elements=dict(model_el_to_gt),
            actions=dict(model_ac_to_gt),
            feedback=dict(model_fb_to_gt),
            groups=dict(model_ig_to_gt),
        )

    out = TempGroundTruthDocument(
        schema_version=config.TEMP_GT_SCHEMA_VERSION,
        annotation_meta=ann,
        image=img,
        screen=screen,
        elements=elements_out,
        actions=actions_out,
        feedback=feedback_out,
        groups=groups_out,
        screen_intents=intents_out,
        unresolved_groups=unresolved_out,
        conversion_report=report,
    )
    sync_conversion_counts(out)
    out.annotation_meta.review_priority = compute_review_priority(
        out.conversion_report,
        unresolved_group_count=len(unresolved_out),
    )
    return out


def _ground_type_a(
    action: Mapping[str, Any],
    element_by_model_id: dict[str, dict[str, Any]],
    model_el_to_gt: dict[str, str],
) -> tuple[list[str], str] | None:
    texts = as_str_list(action.get("text"))
    for _eid, el in element_by_model_id.items():
        el_texts = as_str_list(el.get("text"))
        for at in texts:
            for et in el_texts:
                if text_matches(at, et):
                    gid = model_el_to_gt.get(str(el.get("element_id", "")))
                    if gid:
                        anchors = [t.strip() for t in el_texts if t and str(t).strip()]
                        return (anchors if anchors else [et.strip()], gid)
    return None


def _ground_type_b(
    action: Mapping[str, Any],
    action_to_group: dict[str, dict[str, Any]],
    element_by_model_id: dict[str, dict[str, Any]],
    model_el_to_gt: dict[str, str],
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
                gid = model_el_to_gt.get(str(el.get("element_id", "")))
                if gid:
                    anchors = [t.strip() for t in el_texts if t and str(t).strip()]
                    return (anchors if anchors else [et.strip()], gid)
    return None


def _map_evidence_ref(
    evidence_type: str,
    source_id: str,
    model_el_to_gt: dict[str, str],
    model_ac_to_gt: dict[str, str],
    model_fb_to_gt: dict[str, str],
    model_ig_to_gt: dict[str, str],
) -> str | None:
    if evidence_type == "element_text":
        return model_el_to_gt.get(source_id)
    if evidence_type == "action_text":
        return model_ac_to_gt.get(source_id)
    if evidence_type == "feedback_text":
        return model_fb_to_gt.get(source_id)
    if evidence_type == "group_evidence":
        return model_ig_to_gt.get(source_id)
    if evidence_type == "control_state":
        return model_el_to_gt.get(source_id)
    if evidence_type == "non_text_label":
        return None
    return model_el_to_gt.get(source_id) or model_ac_to_gt.get(source_id)


def _validate_group_membership(
    ui: dict[str, Any],
    model_el_to_gt: dict[str, str],
    model_ac_to_gt: dict[str, str],
    model_fb_to_gt: dict[str, str],
    report: ConversionReport,
) -> None:
    groups = safe_list(ui.get("interaction_groups"))

    def count_el(eid: str) -> int:
        n = 0
        for g in groups:
            gd = safe_dict(g)
            if eid in as_str_list(gd.get("element_ids")):
                n += 1
        return n

    def count_ac(aid: str) -> int:
        n = 0
        for g in groups:
            gd = safe_dict(g)
            if aid in as_str_list(gd.get("action_ids")):
                n += 1
        return n

    def count_fb(fid: str) -> int:
        n = 0
        for g in groups:
            gd = safe_dict(g)
            if fid in as_str_list(gd.get("feedback_ids")):
                n += 1
        return n

    for eid, gtid in model_el_to_gt.items():
        c = count_el(eid)
        if c == 0:
            report.auto_flags.append(f"orphan_element:{gtid}")
        elif c > 1:
            report.auto_flags.append(f"multi_group_element:{gtid}")

    for aid, gtid in model_ac_to_gt.items():
        c = count_ac(aid)
        if c == 0:
            report.auto_flags.append(f"orphan_action:{gtid}")
        elif c > 1:
            report.auto_flags.append(f"multi_group_action:{gtid}")

    for fid, gtid in model_fb_to_gt.items():
        c = count_fb(fid)
        if c == 0:
            report.auto_flags.append(f"orphan_feedback:{gtid}")
        elif c > 1:
            report.auto_flags.append(f"multi_group_feedback:{gtid}")


def try_build_temp_ground_truth(
    doc: ExperimentRawOutputDocument,
    *,
    source_raw_output_path: str,
    validate_joint_schema: bool = True,
) -> tuple[TempGroundTruthDocument | None, str | None]:
    """Returns (doc, None) on success or (None, error_message)."""
    try:
        return (
            build_temp_ground_truth_from_raw(
                doc,
                source_raw_output_path=source_raw_output_path,
                validate_joint_schema=validate_joint_schema,
            ),
            None,
        )
    except ValidationError as exc:
        return None, str(exc)
    except ValueError as exc:
        return None, str(exc)
