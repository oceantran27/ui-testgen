"""Per-image metrics, invalid-reference counts, and micro/macro aggregation."""

from __future__ import annotations

from typing import Any

from app.constants.screen_intent_taxonomy import EVIDENCE_TYPE_VALUES

from experiments.ui_state_extraction import config as ui_state_experiment_config
from experiments.ui_state_extraction.schemas.evaluation_result_schema import (
    ActionMetricsBlock,
    ConsistencyMetricsBlock,
    ElementMetricsBlock,
    FeedbackMetricsBlock,
    GroupMetricsBlock,
    IntentMetricsBlock,
    KeyDiagnosticsBlock,
    PerImageEvaluationResult,
    ScreenMetricsBlock,
)
from experiments.ui_state_extraction.schemas.evaluation_metric_schema import DiagnosticMetrics
from experiments.ui_state_extraction.schemas.evaluation_unit_schema import PredictionEvaluationBundle
from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import TempGroundTruthDocument
from experiments.ui_state_extraction.services.evaluation_key_service import has_evaluable_key
from experiments.ui_state_extraction.services.key_metric_service import (
    compute_multiset_principal_metrics,
    multiset_debug_dict,
)
from experiments.ui_state_extraction.services.ground_truth_normalizer_service import (
    GtEvaluationView,
    build_gt_evaluation_view,
)
from experiments.ui_state_extraction.services.pred_evaluation_view import PredEvaluationView
from experiments.ui_state_extraction.services.prediction_normalizer_service import (
    build_prediction_evaluation_view,
    normalize_raw_model_output,
)
from experiments.ui_state_extraction.services.unit_matching_service import (
    compute_intent_field_metrics,
    grounded_and_all_gt_element_ids,
    match_all_units,
)


def _key_diagnostics_from_views(
    pred_view: PredEvaluationView,
    gt_view: GtEvaluationView,
) -> KeyDiagnosticsBlock:
    pd = pred_view.diagnostics
    gd = gt_view.diagnostics
    return KeyDiagnosticsBlock(
        skipped_empty_key_element_count=pd.skipped_empty_key_element,
        skipped_empty_key_action_count=pd.skipped_empty_key_action,
        skipped_empty_key_feedback_count=pd.skipped_empty_key_feedback,
        intent_key_missing_count=pd.skipped_empty_key_intent + gd.skipped_empty_key_intent,
    )


def _build_key_diagnostics(raw_model_output: dict[str, Any], gt: TempGroundTruthDocument) -> KeyDiagnosticsBlock:
    pred_view = build_prediction_evaluation_view(raw_model_output)
    gt_view = build_gt_evaluation_view(gt)
    return _key_diagnostics_from_views(pred_view, gt_view)


def _safe_div(num: float, den: int) -> float | None:
    if den == 0:
        return None
    return num / den


def _prf(matched: int, pred_n: int, gt_n: int) -> tuple[float | None, float | None, float | None]:
    prec = _safe_div(float(matched), pred_n) if pred_n else None
    rec = _safe_div(float(matched), gt_n) if gt_n else None
    if prec is None or rec is None:
        return prec, rec, None
    if prec + rec == 0:
        return prec, rec, 0.0
    return prec, rec, 2 * prec * rec / (prec + rec)


def _acc(correct: int, total: int) -> float | None:
    return _safe_div(float(correct), total) if total else None


def _element_is_text_grounded(unit: Any) -> bool:
    """True if element has a non-empty evaluation label key (see evaluation_key_service)."""
    return has_evaluable_key(unit, kind="element")


def count_invalid_references(raw_model_output: dict[str, Any]) -> tuple[int, int]:
    """Return (invalid_count, total_checks)."""
    ui = raw_model_output.get("ui_state") if isinstance(raw_model_output, dict) else None
    si = raw_model_output.get("screen_intents") if isinstance(raw_model_output, dict) else None
    ui = ui if isinstance(ui, dict) else {}
    si = si if isinstance(si, dict) else {}

    el_ids = {str(e.get("element_id", "")) for e in (ui.get("visible_elements") or []) if e}
    el_ids.discard("")
    ac_ids = {str(a.get("action_id", "")) for a in (ui.get("available_actions") or []) if a}
    ac_ids.discard("")
    fb_ids = {str(f.get("feedback_id", "")) for f in (ui.get("visible_feedback") or []) if f}
    fb_ids.discard("")
    grp_ids = {str(g.get("group_id", "")) for g in (ui.get("interaction_groups") or []) if g}
    grp_ids.discard("")

    bad = 0
    total = 0

    def chk(ok: bool) -> None:
        nonlocal bad, total
        total += 1
        if not ok:
            bad += 1

    for g in ui.get("interaction_groups") or []:
        if not isinstance(g, dict):
            continue
        for x in g.get("element_ids") or []:
            chk(str(x) in el_ids)
        for x in g.get("action_ids") or []:
            chk(str(x) in ac_ids)
        for x in g.get("feedback_ids") or []:
            chk(str(x) in fb_ids)
        pa = g.get("primary_action_id")
        if pa is not None:
            chk(str(pa) in ac_ids)

    for intent in si.get("screen_behaviour_intents") or []:
        if not isinstance(intent, dict):
            continue
        sg = str(intent.get("source_group_id", ""))
        chk(not sg or sg in grp_ids)
        for key in ("primary_action_id", "commit_action_id"):
            v = intent.get(key)
            if v is not None:
                chk(str(v) in ac_ids)
        for x in intent.get("secondary_action_ids") or []:
            chk(str(x) in ac_ids)
        for x in intent.get("required_input_element_ids") or []:
            chk(str(x) in el_ids)
        for eref in intent.get("evidence_refs") or []:
            if not isinstance(eref, dict):
                chk(False)
                continue
            et = str(eref.get("evidence_type", ""))
            sid = str(eref.get("source_id", ""))
            total += 1
            if et not in EVIDENCE_TYPE_VALUES:
                bad += 1
                continue
            if et == "non_text_label":
                continue
            ok = False
            if et == "element_text":
                ok = sid in el_ids
            elif et == "action_text":
                ok = sid in ac_ids
            elif et == "feedback_text":
                ok = sid in fb_ids
            elif et == "group_evidence":
                ok = sid in grp_ids
            elif et == "control_state":
                ok = sid in el_ids
            if not ok:
                bad += 1
        templates = intent.get("local_action_sequence_templates") or []
        if templates and isinstance(templates[0], dict):
            for st in templates[0].get("steps") or []:
                if not isinstance(st, dict):
                    continue
                sa = st.get("source_action_id")
                se = st.get("source_element_id")
                if sa is not None:
                    chk(str(sa) in ac_ids)
                if se is not None:
                    chk(str(se) in el_ids)

    return bad, total


def evaluate_pair_using_key_counters(
    gt: TempGroundTruthDocument,
    raw_model_output: dict[str, Any],
    *,
    group_jaccard_threshold: float = 0.6,
    include_debug: bool = False,
) -> PerImageEvaluationResult:
    """Multiset Counter PRF for element/action/feedback/intent; screen enums without domain."""
    _ = group_jaccard_threshold
    bundle, pred_view, gt_view = compute_multiset_principal_metrics(raw_model_output, gt)
    pred_bundle = normalize_raw_model_output(raw_model_output)

    el, acm, fb, itp = bundle.element, bundle.action, bundle.feedback, bundle.intent
    sf_int = bundle.presentation_scope_correct + bundle.screen_type_correct + bundle.outcome_state_type_correct
    screen_block = ScreenMetricsBlock(
        total_fields=3,
        correct_fields=sf_int,
        accuracy=_acc(sf_int, 3),
        presentation_scope_match=bundle.presentation_scope_correct,
        screen_type_match=bundle.screen_type_correct,
        outcome_state_type_match=bundle.outcome_state_type_correct,
        screen_enum_mean_accuracy=bundle.screen_enum_accuracy,
    )

    pe_n = len(pred_bundle.elements)
    ge_n = len(gt.elements)
    tg_pred_diag = pred_view.diagnostics.skipped_empty_key_element
    tg_gt_diag = gt_view.diagnostics.skipped_empty_key_element
    el_metrics = ElementMetricsBlock(
        gt_count=el.gt_count,
        pred_count=el.pred_count,
        matched_count=el.correct_count,
        text_grounded_gt_count=el.gt_count,
        text_grounded_pred_count=el.pred_count,
        text_grounded_matched_count=el.correct_count,
        pred_empty_anchor_element_count=tg_pred_diag,
        gt_empty_anchor_element_count=tg_gt_diag,
        empty_anchor_element_delta=abs(tg_pred_diag - tg_gt_diag),
        pred_empty_anchor_element_rate=_acc(tg_pred_diag, pe_n),
        gt_empty_anchor_element_rate=_acc(tg_gt_diag, ge_n),
        precision=el.precision,
        recall=el.recall,
        f1=el.f1,
        element_type_accuracy=None,
        role_hint_accuracy=None,
        visual_region_accuracy=None,
    )

    action_metrics = ActionMetricsBlock(
        gt_count=acm.gt_count,
        pred_count=acm.pred_count,
        matched_count=acm.correct_count,
        action_grounding_evaluated_count=0,
        precision=acm.precision,
        recall=acm.recall,
        f1=acm.f1,
        action_type_accuracy=None,
        action_priority_accuracy=None,
        action_region_accuracy=None,
        action_grounding_accuracy=None,
    )

    feedback_metrics = FeedbackMetricsBlock(
        gt_count=fb.gt_count,
        pred_count=fb.pred_count,
        matched_count=fb.correct_count,
        precision=fb.precision,
        recall=fb.recall,
        f1=fb.f1,
        feedback_type_accuracy=None,
        feedback_related_element_accuracy=None,
        feedback_related_empty_anchor_excluded_pred_refs=0,
        feedback_related_empty_anchor_excluded_gt_refs=0,
    )

    pg_n = len(pred_bundle.groups)
    gg_n = len(gt.groups)
    group_metrics = GroupMetricsBlock(
        gt_count=gg_n,
        pred_count=pg_n,
        matched_count=0,
        precision=None,
        recall=None,
        f1=None,
        group_membership_precision=None,
        group_membership_recall=None,
        group_membership_f1=None,
        group_type_accuracy=None,
        primary_action_accuracy=None,
        group_membership_empty_anchor_excluded_pred_refs=0,
        group_membership_empty_anchor_excluded_gt_refs=0,
    )


    intent_metrics = IntentMetricsBlock(
        gt_count=itp.gt_count,
        pred_count=itp.pred_count,
        matched_count=itp.correct_count,
        precision=itp.precision,
        recall=itp.recall,
        f1=itp.f1,
        intent_kind_accuracy=None,
        intent_source_group_accuracy=None,
        intent_primary_action_accuracy=None,
        intent_commit_action_accuracy=None,
        required_input_precision=None,
        required_input_recall=None,
        required_input_f1=None,
        required_input_correct_count=0,
        required_input_pred_count=0,
        required_input_gt_count=0,
        required_input_empty_anchor_excluded_gt_refs=0,
        required_input_empty_anchor_excluded_pred_refs=0,
        evidence_target_precision=None,
        evidence_target_recall=None,
        evidence_target_f1=None,
        evidence_target_correct_count=0,
        evidence_target_pred_count=0,
        evidence_target_gt_count=0,
        evidence_empty_anchor_excluded_gt_refs=0,
        evidence_empty_anchor_excluded_pred_refs=0,
        step_grounding_accuracy=None,
        step_precision=None,
        step_recall=None,
        step_f1=None,
        step_correct_count=0,
        step_pred_count=0,
        step_gt_count=0,
        step_empty_anchor_excluded_count=0,
    )

    inv_bad, inv_tot = count_invalid_references(raw_model_output)
    total_pred_units = (
        len(pred_bundle.elements)
        + len(pred_bundle.actions)
        + len(pred_bundle.feedback)
        + len(pred_bundle.groups)
        + len(pred_bundle.intents)
    )
    h_el = max(0, el.pred_count - el.correct_count)
    h_ac = max(0, acm.pred_count - acm.correct_count)
    h_fb = max(0, fb.pred_count - fb.correct_count)
    h_in = max(0, itp.pred_count - itp.correct_count)
    h_gr = len(pred_bundle.groups)
    hall_u = h_el + h_ac + h_fb + h_gr + h_in
    cons = ConsistencyMetricsBlock(
        invalid_reference_count=inv_bad,
        total_references_checked=inv_tot,
        invalid_reference_rate=_acc(inv_bad, inv_tot),
        hallucinated_element_count=h_el,
        hallucinated_action_count=h_ac,
        hallucinated_feedback_count=h_fb,
        hallucinated_group_count=h_gr,
        hallucinated_intent_count=h_in,
        hallucinated_unit_count=hall_u,
        total_pred_units=total_pred_units,
        hallucination_rate=_acc(hall_u, total_pred_units),
    )

    dbg: dict[str, Any] = {}
    if include_debug:
        dbg = {
            "keyMultiset": multiset_debug_dict(bundle, pred_view, gt_view),
            "prediction_auto_flags": pred_bundle.auto_flags,
        }

    return PerImageEvaluationResult(
        image_id=gt.image.image_id,
        relative_path=gt.image.relative_path,
        status="evaluated",
        screen_metrics=screen_block,
        element_metrics=el_metrics,
        action_metrics=action_metrics,
        feedback_metrics=feedback_metrics,
        group_metrics=group_metrics,
        intent_metrics=intent_metrics,
        consistency_metrics=cons,
        key_diagnostics=_key_diagnostics_from_views(pred_view, gt_view),
        debug=dbg,
    )


def evaluate_pair(
    pred: PredictionEvaluationBundle,
    gt: TempGroundTruthDocument,
    raw_model_output: dict[str, Any],
    *,
    group_jaccard_threshold: float,
    include_debug: bool,
    use_key_counters: bool | None = None,
) -> PerImageEvaluationResult:
    """Evaluate prediction vs GT. Multiset Counter PRF when ``use_key_counters=True`` or config MODULE3_USE_PRED... (pred unused on that path)."""
    key_metrics = getattr(ui_state_experiment_config, "MODULE3_USE_PRED_EVAL_VIEW_FOR_MAIN_METRICS", False)
    if use_key_counters is not None:
        key_metrics = use_key_counters
    if key_metrics:
        return evaluate_pair_using_key_counters(
            gt,
            raw_model_output,
            group_jaccard_threshold=group_jaccard_threshold,
            include_debug=include_debug,
        )
    m = match_all_units(pred, gt, group_jaccard_threshold=group_jaccard_threshold)
    grounded_gt_el_ids, all_gt_el_ids = grounded_and_all_gt_element_ids(gt)

    # Screen (three enums; domain excluded — Sprint 6 / greedy parity with key-metrics path)
    psc_match = pred.screen.presentation_scope == gt.screen.presentation_scope
    st_match = pred.screen.screen_type == gt.screen.screen_type
    ost_match = pred.screen.outcome_state_type == gt.screen.outcome_state_type
    sf = int(psc_match) + int(st_match) + int(ost_match)
    screen_block = ScreenMetricsBlock(
        total_fields=3,
        correct_fields=sf,
        accuracy=_acc(sf, 3),
        presentation_scope_match=psc_match,
        screen_type_match=st_match,
        outcome_state_type_match=ost_match,
        screen_enum_mean_accuracy=_acc(sf, 3),
    )

    p_en, g_en = len(pred.elements), len(gt.elements)
    tg_pred_n = sum(1 for pe in pred.elements if _element_is_text_grounded(pe))
    tg_gt_n = sum(1 for ge in gt.elements if _element_is_text_grounded(ge))
    pred_empty_n = p_en - tg_pred_n
    gt_empty_n = g_en - tg_gt_n
    tg_matched = sum(
        1
        for pe in pred.elements
        if _element_is_text_grounded(pe) and pe.pred_element_id in m.pred_to_gt_element
    )
    el_p, el_r, el_f1 = _prf(tg_matched, tg_pred_n, tg_gt_n)

    el_type_ok = el_rh_ok = el_v_ok = 0
    for row in m.element_rows:
        if not row.get("gt_element_id"):
            continue
        pred_row = next((x for x in pred.elements if x.pred_element_id == row["pred_element_id"]), None)
        if not pred_row or not _element_is_text_grounded(pred_row):
            continue
        if row.get("element_type_correct"):
            el_type_ok += 1
        if row.get("role_hint_correct"):
            el_rh_ok += 1
        if row.get("visual_region_correct"):
            el_v_ok += 1
    em = tg_matched
    el_metrics = ElementMetricsBlock(
        gt_count=g_en,
        pred_count=p_en,
        matched_count=tg_matched,
        text_grounded_pred_count=tg_pred_n,
        text_grounded_gt_count=tg_gt_n,
        text_grounded_matched_count=tg_matched,
        pred_empty_anchor_element_count=pred_empty_n,
        gt_empty_anchor_element_count=gt_empty_n,
        empty_anchor_element_delta=abs(pred_empty_n - gt_empty_n),
        pred_empty_anchor_element_rate=_acc(pred_empty_n, p_en),
        gt_empty_anchor_element_rate=_acc(gt_empty_n, g_en),
        precision=el_p,
        recall=el_r,
        f1=el_f1,
        element_type_accuracy=_acc(el_type_ok, em),
        role_hint_accuracy=_acc(el_rh_ok, em),
        visual_region_accuracy=_acc(el_v_ok, em),
    )

    matched_ac = len(m.pred_to_gt_action)
    p_an, g_an = len(pred.actions), len(gt.actions)
    ac_p, ac_r, ac_f1 = _prf(matched_ac, p_an, g_an)
    at_ok = ap_ok = ar_ok = agr_ok = agr_n = 0
    for row in m.action_rows:
        if not row.get("gt_action_id"):
            continue
        if row.get("action_type_correct"):
            at_ok += 1
        gt_row = next((x for x in gt.actions if x.gt_action_id == row["gt_action_id"]), None)
        pred_row = next((x for x in pred.actions if x.pred_action_id == row["pred_action_id"]), None)
        if gt_row and pred_row:
            if (pred_row.action_priority or None) == (gt_row.action_priority or None):
                ap_ok += 1
            if pred_row.visual_region == gt_row.visual_region:
                ar_ok += 1
            g_gnd = gt_row.grounded_element_id
            if (
                g_gnd
                and g_gnd in all_gt_el_ids
                and g_gnd not in grounded_gt_el_ids
            ):
                pass
            else:
                agr_n += 1
                if row.get("grounding_correct"):
                    agr_ok += 1
    am = matched_ac
    action_metrics = ActionMetricsBlock(
        gt_count=g_an,
        pred_count=p_an,
        matched_count=matched_ac,
        action_grounding_evaluated_count=agr_n,
        precision=ac_p,
        recall=ac_r,
        f1=ac_f1,
        action_type_accuracy=_acc(at_ok, am),
        action_priority_accuracy=_acc(ap_ok, am),
        action_region_accuracy=_acc(ar_ok, am),
        action_grounding_accuracy=_acc(agr_ok, agr_n),
    )

    matched_fb = len(m.pred_to_gt_feedback)
    p_fn, g_fn = len(pred.feedback), len(gt.feedback)
    fb_p, fb_r, fb_f1 = _prf(matched_fb, p_fn, g_fn)
    ft_ok = frel_ok = fb_ex_p = fb_ex_g = 0
    for row in m.feedback_rows:
        if row.get("gt_feedback_id"):
            if row.get("feedback_type_correct"):
                ft_ok += 1
            if row.get("related_elements_correct"):
                frel_ok += 1
            fb_ex_p += int(row.get("related_empty_anchor_excluded_pred") or 0)
            fb_ex_g += int(row.get("related_empty_anchor_excluded_gt") or 0)
    fm = matched_fb
    feedback_metrics = FeedbackMetricsBlock(
        gt_count=g_fn,
        pred_count=p_fn,
        matched_count=matched_fb,
        precision=fb_p,
        recall=fb_r,
        f1=fb_f1,
        feedback_type_accuracy=_acc(ft_ok, fm),
        feedback_related_element_accuracy=_acc(frel_ok, fm),
        feedback_related_empty_anchor_excluded_pred_refs=fb_ex_p,
        feedback_related_empty_anchor_excluded_gt_refs=fb_ex_g,
    )

    matched_gr = len(m.pred_to_gt_group)
    p_gn, g_gn = len(pred.groups), len(gt.groups)
    gr_p, gr_r, gr_f1 = _prf(matched_gr, p_gn, g_gn)
    gt_ok = gp_ok = gr_ex_p = gr_ex_g = 0
    mf_sum = 0.0
    mf_n = 0
    for row in m.group_rows:
        if row.get("gt_group_id"):
            if row.get("group_type_correct"):
                gt_ok += 1
            if row.get("primary_action_correct"):
                gp_ok += 1
            if row.get("membership_f1") is not None:
                mf_sum += float(row["membership_f1"])
                mf_n += 1
            gr_ex_p += int(row.get("membership_empty_anchor_excluded_pred") or 0)
            gr_ex_g += int(row.get("membership_empty_anchor_excluded_gt") or 0)
    gm = matched_gr
    group_metrics = GroupMetricsBlock(
        gt_count=g_gn,
        pred_count=p_gn,
        matched_count=matched_gr,
        precision=gr_p,
        recall=gr_r,
        f1=gr_f1,
        group_membership_precision=None,
        group_membership_recall=None,
        group_membership_f1=(mf_sum / mf_n) if mf_n else None,
        group_type_accuracy=_acc(gt_ok, gm),
        primary_action_accuracy=_acc(gp_ok, gm),
        group_membership_empty_anchor_excluded_pred_refs=gr_ex_p,
        group_membership_empty_anchor_excluded_gt_refs=gr_ex_g,
    )

    matched_int = len(m.pred_intent_index_to_gt_intent)
    p_in, g_in = len(pred.intents), len(gt.screen_intents)
    in_p, in_r, in_f1 = _prf(matched_int, p_in, g_in)

    ik_ok = isg_ok = ip_ok = ic_ok = 0
    ri_correct_tot = ri_pred_tot = ri_gt_tot = 0
    ev_correct_tot = ev_pred_tot = ev_gt_tot = 0
    st_correct_tot = st_pred_tot = st_gt_tot = 0
    ri_ex_g = ri_ex_p = ev_ex_g = ev_ex_p = st_ex = 0

    el_m, ac_m, fb_m, ig_m = (
        m.pred_to_gt_element,
        m.pred_to_gt_action,
        m.pred_to_gt_feedback,
        m.pred_to_gt_group,
    )

    for p_int in pred.intents:
        g_int = m.pred_intent_index_to_gt_intent.get(p_int.pred_intent_index)
        ir = next((r for r in m.intent_rows if r.get("pred_intent_index") == p_int.pred_intent_index), {})
        if not g_int:
            continue
        ik_ok += 1 if p_int.intent_kind == g_int.intent_kind else 0
        isg_ok += 1 if ig_m.get(p_int.source_pred_group_id) == g_int.source_group_id else 0
        pm = ac_m.get(p_int.primary_pred_action_id) if p_int.primary_pred_action_id else None
        if g_int.primary_action_id:
            ip_ok += 1 if pm == g_int.primary_action_id else 0
        else:
            ip_ok += 1 if pm is None else 0

        cmid = ac_m.get(p_int.commit_pred_action_id) if p_int.commit_pred_action_id else None
        if g_int.commit_action_id:
            ic_ok += 1 if cmid == g_int.commit_action_id else 0
        else:
            ic_ok += 1 if cmid is None else 0

        fields = compute_intent_field_metrics(p_int, g_int, el_m, ac_m, fb_m, ig_m, gt)
        ri_correct_tot += int(fields.get("required_input_correct_count") or 0)
        ri_pred_tot += int(fields.get("required_input_pred_count") or 0)
        ri_gt_tot += int(fields.get("required_input_gt_count") or 0)
        ev_correct_tot += int(fields.get("evidence_target_correct_count") or 0)
        ev_pred_tot += int(fields.get("evidence_target_pred_count") or 0)
        ev_gt_tot += int(fields.get("evidence_target_gt_count") or 0)
        st_correct_tot += int(fields.get("step_correct_count") or 0)
        st_pred_tot += int(fields.get("step_pred_count") or 0)
        st_gt_tot += int(fields.get("step_gt_count") or 0)
        ri_ex_g += int(fields.get("required_input_empty_anchor_excluded_gt_refs") or 0)
        ri_ex_p += int(fields.get("required_input_empty_anchor_excluded_pred_refs") or 0)
        ev_ex_g += int(fields.get("evidence_empty_anchor_excluded_gt_refs") or 0)
        ev_ex_p += int(fields.get("evidence_empty_anchor_excluded_pred_refs") or 0)
        st_ex += int(fields.get("step_empty_anchor_excluded_count") or 0)
        ir["required_input_correct_count"] = fields.get("required_input_correct_count")
        ir["required_input_pred_count"] = fields.get("required_input_pred_count")
        ir["required_input_gt_count"] = fields.get("required_input_gt_count")
        ir["required_input_precision"] = fields.get("required_input_precision")
        ir["required_input_recall"] = fields.get("required_input_recall")
        ir["required_input_f1"] = fields.get("required_input_f1")
        ir["evidence_target_correct_count"] = fields.get("evidence_target_correct_count")
        ir["evidence_target_pred_count"] = fields.get("evidence_target_pred_count")
        ir["evidence_target_gt_count"] = fields.get("evidence_target_gt_count")
        ir["evidence_target_precision"] = fields.get("evidence_target_precision")
        ir["evidence_target_recall"] = fields.get("evidence_target_recall")
        ir["evidence_target_f1"] = fields.get("evidence_target_f1")
        ir["step_correct_count"] = fields.get("step_correct_count")
        ir["step_pred_count"] = fields.get("step_pred_count")
        ir["step_gt_count"] = fields.get("step_gt_count")
        ir["step_precision"] = fields.get("step_precision")
        ir["step_recall"] = fields.get("step_recall")
        ir["step_f1"] = fields.get("step_f1")
        ir["step_grounding_accuracy"] = fields.get("step_grounding_accuracy")
        ir["step_debug"] = fields.get("step_debug")

    ri_p, ri_r, ri_f1 = _prf(ri_correct_tot, ri_pred_tot, ri_gt_tot)
    ev_p, ev_r, ev_f1 = _prf(ev_correct_tot, ev_pred_tot, ev_gt_tot)
    st_p, st_r, st_f1 = _prf(st_correct_tot, st_pred_tot, st_gt_tot)

    im = matched_int
    intent_metrics = IntentMetricsBlock(
        gt_count=g_in,
        pred_count=p_in,
        matched_count=matched_int,
        precision=in_p,
        recall=in_r,
        f1=in_f1,
        intent_kind_accuracy=_acc(ik_ok, im),
        intent_source_group_accuracy=_acc(isg_ok, im),
        intent_primary_action_accuracy=_acc(ip_ok, im),
        intent_commit_action_accuracy=_acc(ic_ok, im),
        required_input_precision=ri_p,
        required_input_recall=ri_r,
        required_input_f1=ri_f1,
        required_input_correct_count=ri_correct_tot,
        required_input_pred_count=ri_pred_tot,
        required_input_gt_count=ri_gt_tot,
        required_input_empty_anchor_excluded_gt_refs=ri_ex_g,
        required_input_empty_anchor_excluded_pred_refs=ri_ex_p,
        evidence_target_precision=ev_p,
        evidence_target_recall=ev_r,
        evidence_target_f1=ev_f1,
        evidence_target_correct_count=ev_correct_tot,
        evidence_target_pred_count=ev_pred_tot,
        evidence_target_gt_count=ev_gt_tot,
        evidence_empty_anchor_excluded_gt_refs=ev_ex_g,
        evidence_empty_anchor_excluded_pred_refs=ev_ex_p,
        step_grounding_accuracy=st_f1,
        step_precision=st_p,
        step_recall=st_r,
        step_f1=st_f1,
        step_correct_count=st_correct_tot,
        step_pred_count=st_pred_tot,
        step_gt_count=st_gt_tot,
        step_empty_anchor_excluded_count=st_ex,
    )

    inv_bad, inv_tot = count_invalid_references(raw_model_output)

    h_el = tg_pred_n - tg_matched
    h_ac = p_an - matched_ac
    h_fb = p_fn - matched_fb
    h_gr = p_gn - matched_gr
    h_in = p_in - matched_int
    total_pred_u = p_en + p_an + p_fn + p_gn + p_in
    hall_u = h_el + h_ac + h_fb + h_gr + h_in

    cons = ConsistencyMetricsBlock(
        invalid_reference_count=inv_bad,
        total_references_checked=inv_tot,
        invalid_reference_rate=_acc(inv_bad, inv_tot),
        hallucinated_element_count=h_el,
        hallucinated_action_count=h_ac,
        hallucinated_feedback_count=h_fb,
        hallucinated_group_count=h_gr,
        hallucinated_intent_count=h_in,
        hallucinated_unit_count=hall_u,
        total_pred_units=total_pred_u,
        hallucination_rate=_acc(hall_u, total_pred_u),
    )

    dbg: dict[str, Any] = {}
    if include_debug:
        dbg = {
            "element_matches": m.element_rows,
            "action_matches": m.action_rows,
            "feedback_matches": m.feedback_rows,
            "group_matches": m.group_rows,
            "intent_matches": m.intent_rows,
            "unmatched_predictions": {
                "elements": [r["pred_element_id"] for r in m.element_rows if not r.get("gt_element_id")],
                "actions": [r["pred_action_id"] for r in m.action_rows if not r.get("gt_action_id")],
                "feedback": [r["pred_feedback_id"] for r in m.feedback_rows if not r.get("gt_feedback_id")],
                "groups": [r["pred_group_id"] for r in m.group_rows if not r.get("gt_group_id")],
                "intent_indices": [
                    r["pred_intent_index"] for r in m.intent_rows if not r.get("gt_intent_id")
                ],
            },
            "prediction_auto_flags": pred.auto_flags,
        }

    return PerImageEvaluationResult(
        image_id=gt.image.image_id,
        relative_path=gt.image.relative_path,
        status="evaluated",
        screen_metrics=screen_block,
        element_metrics=el_metrics,
        action_metrics=action_metrics,
        feedback_metrics=feedback_metrics,
        group_metrics=group_metrics,
        intent_metrics=intent_metrics,
        consistency_metrics=cons,
        key_diagnostics=_build_key_diagnostics(raw_model_output, gt),
        debug=dbg,
    )


def _mean(vals: list[float | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    if not xs:
        return None
    return sum(xs) / len(xs)


def micro_macro_from_per_image(
    results: list[PerImageEvaluationResult],
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """Return (micro_metrics, macro_metrics) flat dicts for legacy diagnostic use (see DiagnosticMetrics)."""
    if not results:
        return {}, {}

    el_matched = sum(r.element_metrics.text_grounded_matched_count for r in results)
    el_pred = sum(r.element_metrics.text_grounded_pred_count for r in results)
    el_gt = sum(r.element_metrics.text_grounded_gt_count for r in results)
    el_mic_p, el_mic_r, el_mic_f1 = _prf(el_matched, el_pred, el_gt)

    pe_sum = sum(r.element_metrics.pred_empty_anchor_element_count for r in results)
    ge_sum = sum(r.element_metrics.gt_empty_anchor_element_count for r in results)
    p_tot = sum(r.element_metrics.pred_count for r in results)
    g_tot = sum(r.element_metrics.gt_count for r in results)

    ac_matched = sum(r.action_metrics.matched_count for r in results)
    ac_pred = sum(r.action_metrics.pred_count for r in results)
    ac_gt = sum(r.action_metrics.gt_count for r in results)
    ac_mic_p, ac_mic_r, ac_mic_f1 = _prf(ac_matched, ac_pred, ac_gt)

    fb_matched = sum(r.feedback_metrics.matched_count for r in results)
    fb_pred = sum(r.feedback_metrics.pred_count for r in results)
    fb_gt = sum(r.feedback_metrics.gt_count for r in results)
    fb_mic_p, fb_mic_r, fb_mic_f1 = _prf(fb_matched, fb_pred, fb_gt)

    gr_matched = sum(r.group_metrics.matched_count for r in results)
    gr_pred = sum(r.group_metrics.pred_count for r in results)
    gr_gt = sum(r.group_metrics.gt_count for r in results)
    gr_mic_p, gr_mic_r, gr_mic_f1 = _prf(gr_matched, gr_pred, gr_gt)

    in_matched = sum(r.intent_metrics.matched_count for r in results)
    in_pred = sum(r.intent_metrics.pred_count for r in results)
    in_gt = sum(r.intent_metrics.gt_count for r in results)
    in_mic_p, in_mic_r, in_mic_f1 = _prf(in_matched, in_pred, in_gt)

    screen_correct = sum(r.screen_metrics.correct_fields for r in results)
    screen_tot = sum(r.screen_metrics.total_fields for r in results)

    micro: dict[str, float | None] = {
        "screen_enum_accuracy": _acc(screen_correct, screen_tot),
        "element_precision": el_mic_p,
        "element_recall": el_mic_r,
        "element_f1": el_mic_f1,
        "text_grounded_matched_count": float(el_matched),
        "text_grounded_pred_count": float(el_pred),
        "text_grounded_gt_count": float(el_gt),
        "pred_empty_anchor_element_count": float(pe_sum),
        "gt_empty_anchor_element_count": float(ge_sum),
        "empty_anchor_element_delta": float(abs(pe_sum - ge_sum)),
        "pred_empty_anchor_element_rate": _acc(pe_sum, p_tot),
        "gt_empty_anchor_element_rate": _acc(ge_sum, g_tot),
        "action_precision": ac_mic_p,
        "action_recall": ac_mic_r,
        "action_f1": ac_mic_f1,
        "action_grounding_evaluated_count": float(
            sum(r.action_metrics.action_grounding_evaluated_count for r in results),
        ),
        "feedback_precision": fb_mic_p,
        "feedback_recall": fb_mic_r,
        "feedback_f1": fb_mic_f1,
        "group_precision": gr_mic_p,
        "group_recall": gr_mic_r,
        "group_f1": gr_mic_f1,
        "intent_precision": in_mic_p,
        "intent_recall": in_mic_r,
        "intent_f1": in_mic_f1,
    }

    # Micro accuracies: pool text-grounded matched units
    et_m = sum(r.element_metrics.text_grounded_matched_count for r in results)
    et_num = sum(
        (r.element_metrics.element_type_accuracy or 0.0) * r.element_metrics.text_grounded_matched_count
        for r in results
        if r.element_metrics.text_grounded_matched_count
    )
    micro["element_type_accuracy"] = (et_num / et_m) if et_m else None
    rh_num = sum(
        (r.element_metrics.role_hint_accuracy or 0.0) * r.element_metrics.text_grounded_matched_count
        for r in results
        if r.element_metrics.text_grounded_matched_count
    )
    micro["role_hint_accuracy"] = (rh_num / et_m) if et_m else None
    vr_num = sum(
        (r.element_metrics.visual_region_accuracy or 0.0) * r.element_metrics.text_grounded_matched_count
        for r in results
        if r.element_metrics.text_grounded_matched_count
    )
    micro["element_region_accuracy"] = (vr_num / et_m) if et_m else None

    am = sum(r.action_metrics.matched_count for r in results)
    for field, attr in [
        ("action_type_accuracy", "action_type_accuracy"),
        ("action_priority_accuracy", "action_priority_accuracy"),
        ("action_region_accuracy", "action_region_accuracy"),
    ]:
        num = sum(
            (getattr(r.action_metrics, attr) or 0.0) * r.action_metrics.matched_count
            for r in results
            if r.action_metrics.matched_count
        )
        micro[field] = (num / am) if am else None
    agr_den = sum(r.action_metrics.action_grounding_evaluated_count for r in results)
    agr_num = sum(
        (r.action_metrics.action_grounding_accuracy or 0.0) * r.action_metrics.action_grounding_evaluated_count
        for r in results
        if r.action_metrics.action_grounding_evaluated_count
    )
    micro["action_grounding_accuracy"] = (agr_num / agr_den) if agr_den else None

    fm = sum(r.feedback_metrics.matched_count for r in results)
    for field, attr in [
        ("feedback_type_accuracy", "feedback_type_accuracy"),
        ("feedback_related_element_accuracy", "feedback_related_element_accuracy"),
    ]:
        num = sum(
            (getattr(r.feedback_metrics, attr) or 0.0) * r.feedback_metrics.matched_count
            for r in results
            if r.feedback_metrics.matched_count
        )
        micro[field] = (num / fm) if fm else None

    gm = sum(r.group_metrics.matched_count for r in results)
    micro["group_type_accuracy"] = (
        sum(
            (r.group_metrics.group_type_accuracy or 0.0) * r.group_metrics.matched_count
            for r in results
            if r.group_metrics.matched_count
        )
        / gm
        if gm
        else None
    )
    micro["group_primary_action_accuracy"] = (
        sum(
            (r.group_metrics.primary_action_accuracy or 0.0) * r.group_metrics.matched_count
            for r in results
            if r.group_metrics.matched_count
        )
        / gm
        if gm
        else None
    )
    if gm:
        s_mem = sum(
            (r.group_metrics.group_membership_f1 or 0.0) * r.group_metrics.matched_count
            for r in results
            if r.group_metrics.matched_count
        )
        micro["group_membership_f1"] = s_mem / gm
    else:
        micro["group_membership_f1"] = None

    im = sum(r.intent_metrics.matched_count for r in results)
    intent_acc_fields = [
        ("intent_kind_accuracy", "intent_kind_accuracy"),
        ("intent_source_group_accuracy", "intent_source_group_accuracy"),
        ("intent_primary_action_accuracy", "intent_primary_action_accuracy"),
        ("intent_commit_action_accuracy", "intent_commit_action_accuracy"),
    ]
    for field, attr in intent_acc_fields:
        s = sum(
            (getattr(r.intent_metrics, attr) or 0.0) * r.intent_metrics.matched_count
            for r in results
            if r.intent_metrics.matched_count
        )
        micro[field] = (s / im) if im else None
    micro["commit_action_accuracy"] = micro.get("intent_commit_action_accuracy")

    ri_correct_ds = sum(r.intent_metrics.required_input_correct_count for r in results)
    ri_pred_ds = sum(r.intent_metrics.required_input_pred_count for r in results)
    ri_gt_ds = sum(r.intent_metrics.required_input_gt_count for r in results)
    ri_mic_p, ri_mic_r, ri_mic_f1 = _prf(ri_correct_ds, ri_pred_ds, ri_gt_ds)
    micro["required_input_precision"] = ri_mic_p
    micro["required_input_recall"] = ri_mic_r
    micro["required_input_f1"] = ri_mic_f1
    micro["required_input_correct_count"] = float(ri_correct_ds)
    micro["required_input_pred_count"] = float(ri_pred_ds)
    micro["required_input_gt_count"] = float(ri_gt_ds)

    ev_correct_ds = sum(r.intent_metrics.evidence_target_correct_count for r in results)
    ev_pred_ds = sum(r.intent_metrics.evidence_target_pred_count for r in results)
    ev_gt_ds = sum(r.intent_metrics.evidence_target_gt_count for r in results)
    ev_mic_p, ev_mic_r, ev_mic_f1 = _prf(ev_correct_ds, ev_pred_ds, ev_gt_ds)
    micro["evidence_target_precision"] = ev_mic_p
    micro["evidence_target_recall"] = ev_mic_r
    micro["evidence_target_f1"] = ev_mic_f1
    micro["evidence_target_correct_count"] = float(ev_correct_ds)
    micro["evidence_target_pred_count"] = float(ev_pred_ds)
    micro["evidence_target_gt_count"] = float(ev_gt_ds)

    st_correct_ds = sum(r.intent_metrics.step_correct_count for r in results)
    st_pred_ds = sum(r.intent_metrics.step_pred_count for r in results)
    st_gt_ds = sum(r.intent_metrics.step_gt_count for r in results)
    st_mic_p, st_mic_r, st_mic_f1 = _prf(st_correct_ds, st_pred_ds, st_gt_ds)
    micro["step_precision"] = st_mic_p
    micro["step_recall"] = st_mic_r
    micro["step_f1"] = st_mic_f1
    micro["step_grounding_accuracy"] = st_mic_f1
    micro["step_correct_count"] = float(st_correct_ds)
    micro["step_pred_count"] = float(st_pred_ds)
    micro["step_gt_count"] = float(st_gt_ds)
    inv_b = sum(r.consistency_metrics.invalid_reference_count for r in results)
    inv_t = sum(r.consistency_metrics.total_references_checked for r in results)
    micro["invalid_reference_rate"] = _acc(inv_b, inv_t) if inv_t else None
    hall = sum(r.consistency_metrics.hallucinated_unit_count for r in results)
    tot_u = sum(r.consistency_metrics.total_pred_units for r in results)
    micro["hallucination_rate"] = _acc(hall, tot_u) if tot_u else None

    micro["required_input_empty_anchor_excluded_gt_refs"] = float(
        sum(r.intent_metrics.required_input_empty_anchor_excluded_gt_refs for r in results),
    )
    micro["required_input_empty_anchor_excluded_pred_refs"] = float(
        sum(r.intent_metrics.required_input_empty_anchor_excluded_pred_refs for r in results),
    )
    micro["evidence_empty_anchor_excluded_gt_refs"] = float(
        sum(r.intent_metrics.evidence_empty_anchor_excluded_gt_refs for r in results),
    )
    micro["evidence_empty_anchor_excluded_pred_refs"] = float(
        sum(r.intent_metrics.evidence_empty_anchor_excluded_pred_refs for r in results),
    )
    micro["step_empty_anchor_excluded_count"] = float(
        sum(r.intent_metrics.step_empty_anchor_excluded_count for r in results),
    )
    micro["feedback_related_empty_anchor_excluded_pred_refs"] = float(
        sum(r.feedback_metrics.feedback_related_empty_anchor_excluded_pred_refs for r in results),
    )
    micro["feedback_related_empty_anchor_excluded_gt_refs"] = float(
        sum(r.feedback_metrics.feedback_related_empty_anchor_excluded_gt_refs for r in results),
    )
    micro["group_membership_empty_anchor_excluded_pred_refs"] = float(
        sum(r.group_metrics.group_membership_empty_anchor_excluded_pred_refs for r in results),
    )
    micro["group_membership_empty_anchor_excluded_gt_refs"] = float(
        sum(r.group_metrics.group_membership_empty_anchor_excluded_gt_refs for r in results),
    )

    macro: dict[str, float | None] = {
        "screen_enum_accuracy": _mean([r.screen_metrics.accuracy for r in results]),
        "element_f1": _mean([r.element_metrics.f1 for r in results]),
        "element_precision": _mean([r.element_metrics.precision for r in results]),
        "element_recall": _mean([r.element_metrics.recall for r in results]),
        "element_type_accuracy": _mean([r.element_metrics.element_type_accuracy for r in results]),
        "role_hint_accuracy": _mean([r.element_metrics.role_hint_accuracy for r in results]),
        "element_region_accuracy": _mean([r.element_metrics.visual_region_accuracy for r in results]),
        "text_grounded_matched_count": _mean(
            [float(r.element_metrics.text_grounded_matched_count) for r in results],
        ),
        "text_grounded_pred_count": _mean(
            [float(r.element_metrics.text_grounded_pred_count) for r in results],
        ),
        "text_grounded_gt_count": _mean(
            [float(r.element_metrics.text_grounded_gt_count) for r in results],
        ),
        "pred_empty_anchor_element_count": _mean(
            [float(r.element_metrics.pred_empty_anchor_element_count) for r in results],
        ),
        "gt_empty_anchor_element_count": _mean(
            [float(r.element_metrics.gt_empty_anchor_element_count) for r in results],
        ),
        "empty_anchor_element_delta": _mean(
            [float(r.element_metrics.empty_anchor_element_delta) for r in results],
        ),
        "pred_empty_anchor_element_rate": _mean(
            [r.element_metrics.pred_empty_anchor_element_rate for r in results],
        ),
        "gt_empty_anchor_element_rate": _mean(
            [r.element_metrics.gt_empty_anchor_element_rate for r in results],
        ),
        "action_f1": _mean([r.action_metrics.f1 for r in results]),
        "action_precision": _mean([r.action_metrics.precision for r in results]),
        "action_recall": _mean([r.action_metrics.recall for r in results]),
        "action_type_accuracy": _mean([r.action_metrics.action_type_accuracy for r in results]),
        "action_priority_accuracy": _mean([r.action_metrics.action_priority_accuracy for r in results]),
        "action_grounding_accuracy": _mean([r.action_metrics.action_grounding_accuracy for r in results]),
        "action_region_accuracy": _mean([r.action_metrics.action_region_accuracy for r in results]),
        "action_grounding_evaluated_count": _mean(
            [float(r.action_metrics.action_grounding_evaluated_count) for r in results],
        ),
        "feedback_f1": _mean([r.feedback_metrics.f1 for r in results]),
        "feedback_precision": _mean([r.feedback_metrics.precision for r in results]),
        "feedback_recall": _mean([r.feedback_metrics.recall for r in results]),
        "feedback_type_accuracy": _mean([r.feedback_metrics.feedback_type_accuracy for r in results]),
        "feedback_related_element_accuracy": _mean(
            [r.feedback_metrics.feedback_related_element_accuracy for r in results],
        ),
        "group_f1": _mean([r.group_metrics.f1 for r in results]),
        "group_precision": _mean([r.group_metrics.precision for r in results]),
        "group_recall": _mean([r.group_metrics.recall for r in results]),
        "group_membership_f1": _mean([r.group_metrics.group_membership_f1 for r in results]),
        "group_type_accuracy": _mean([r.group_metrics.group_type_accuracy for r in results]),
        "group_primary_action_accuracy": _mean([r.group_metrics.primary_action_accuracy for r in results]),
        "intent_f1": _mean([r.intent_metrics.f1 for r in results]),
        "intent_precision": _mean([r.intent_metrics.precision for r in results]),
        "intent_recall": _mean([r.intent_metrics.recall for r in results]),
        "intent_kind_accuracy": _mean([r.intent_metrics.intent_kind_accuracy for r in results]),
        "intent_source_group_accuracy": _mean([r.intent_metrics.intent_source_group_accuracy for r in results]),
        "intent_primary_action_accuracy": _mean([r.intent_metrics.intent_primary_action_accuracy for r in results]),
        "intent_commit_action_accuracy": _mean([r.intent_metrics.intent_commit_action_accuracy for r in results]),
        "commit_action_accuracy": _mean([r.intent_metrics.intent_commit_action_accuracy for r in results]),
        "required_input_precision": _mean([r.intent_metrics.required_input_precision for r in results]),
        "required_input_recall": _mean([r.intent_metrics.required_input_recall for r in results]),
        "required_input_f1": _mean([r.intent_metrics.required_input_f1 for r in results]),
        "required_input_correct_count": _mean([float(r.intent_metrics.required_input_correct_count) for r in results]),
        "required_input_pred_count": _mean([float(r.intent_metrics.required_input_pred_count) for r in results]),
        "required_input_gt_count": _mean([float(r.intent_metrics.required_input_gt_count) for r in results]),
        "evidence_target_precision": _mean([r.intent_metrics.evidence_target_precision for r in results]),
        "evidence_target_recall": _mean([r.intent_metrics.evidence_target_recall for r in results]),
        "evidence_target_f1": _mean([r.intent_metrics.evidence_target_f1 for r in results]),
        "evidence_target_correct_count": _mean(
            [float(r.intent_metrics.evidence_target_correct_count) for r in results],
        ),
        "evidence_target_pred_count": _mean([float(r.intent_metrics.evidence_target_pred_count) for r in results]),
        "evidence_target_gt_count": _mean([float(r.intent_metrics.evidence_target_gt_count) for r in results]),
        "step_grounding_accuracy": _mean([r.intent_metrics.step_grounding_accuracy for r in results]),
        "step_precision": _mean([r.intent_metrics.step_precision for r in results]),
        "step_recall": _mean([r.intent_metrics.step_recall for r in results]),
        "step_f1": _mean([r.intent_metrics.step_f1 for r in results]),
        "step_correct_count": _mean([float(r.intent_metrics.step_correct_count) for r in results]),
        "step_pred_count": _mean([float(r.intent_metrics.step_pred_count) for r in results]),
        "step_gt_count": _mean([float(r.intent_metrics.step_gt_count) for r in results]),
        "invalid_reference_rate": _mean([r.consistency_metrics.invalid_reference_rate for r in results]),
        "hallucination_rate": _mean([r.consistency_metrics.hallucination_rate for r in results]),
        "required_input_empty_anchor_excluded_gt_refs": _mean(
            [float(r.intent_metrics.required_input_empty_anchor_excluded_gt_refs) for r in results],
        ),
        "required_input_empty_anchor_excluded_pred_refs": _mean(
            [float(r.intent_metrics.required_input_empty_anchor_excluded_pred_refs) for r in results],
        ),
        "evidence_empty_anchor_excluded_gt_refs": _mean(
            [float(r.intent_metrics.evidence_empty_anchor_excluded_gt_refs) for r in results],
        ),
        "evidence_empty_anchor_excluded_pred_refs": _mean(
            [float(r.intent_metrics.evidence_empty_anchor_excluded_pred_refs) for r in results],
        ),
        "step_empty_anchor_excluded_count": _mean(
            [float(r.intent_metrics.step_empty_anchor_excluded_count) for r in results],
        ),
        "feedback_related_empty_anchor_excluded_pred_refs": _mean(
            [float(r.feedback_metrics.feedback_related_empty_anchor_excluded_pred_refs) for r in results],
        ),
        "feedback_related_empty_anchor_excluded_gt_refs": _mean(
            [float(r.feedback_metrics.feedback_related_empty_anchor_excluded_gt_refs) for r in results],
        ),
        "group_membership_empty_anchor_excluded_pred_refs": _mean(
            [float(r.group_metrics.group_membership_empty_anchor_excluded_pred_refs) for r in results],
        ),
        "group_membership_empty_anchor_excluded_gt_refs": _mean(
            [float(r.group_metrics.group_membership_empty_anchor_excluded_gt_refs) for r in results],
        ),
    }

    return micro, macro


def _mean_optional_bool(flags: list[bool | None]) -> float | None:
    vals = [1.0 if f else 0.0 for f in flags if f is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _screen_aggregate_v4_fields(
    results: list[PerImageEvaluationResult],
) -> tuple[float | None, float | None, float | None, float | None]:
    """Mean-per-image accuracies for three screen enums and their arithmetic mean."""
    psc = _mean_optional_bool([r.screen_metrics.presentation_scope_match for r in results])
    stc = _mean_optional_bool([r.screen_metrics.screen_type_match for r in results])
    ost = _mean_optional_bool([r.screen_metrics.outcome_state_type_match for r in results])
    parts = [x for x in (psc, stc, ost) if x is not None]
    screen_enum = sum(parts) / len(parts) if parts else None
    return psc, stc, ost, screen_enum


def _diagnostic_metrics_from_legacy_micro(micro_legacy: dict[str, float | None]) -> DiagnosticMetrics:
    fields = set(DiagnosticMetrics.model_fields.keys())
    return DiagnosticMetrics(**{k: v for k, v in micro_legacy.items() if k in fields})


def aggregate_dataset_metrics_v4(
    results: list[PerImageEvaluationResult],
) -> tuple[dict[str, float | None], dict[str, float | None], DiagnosticMetrics]:
    """Dataset-level Sprint 8 aggregates: v4 micro/macro dicts + legacy pooled diagnostic_metrics."""
    if not results:
        return {}, {}, DiagnosticMetrics()

    micro_legacy, _macro_legacy = micro_macro_from_per_image(results)
    diagnostic = _diagnostic_metrics_from_legacy_micro(micro_legacy)

    psc, stc, ost, screen_enum = _screen_aggregate_v4_fields(results)

    el_c = sum(r.element_metrics.text_grounded_matched_count for r in results)
    el_p = sum(r.element_metrics.text_grounded_pred_count for r in results)
    el_g = sum(r.element_metrics.text_grounded_gt_count for r in results)
    el_mic_p, el_mic_r, el_mic_f1 = _prf(el_c, el_p, el_g)

    ac_c = sum(r.action_metrics.matched_count for r in results)
    ac_p = sum(r.action_metrics.pred_count for r in results)
    ac_g = sum(r.action_metrics.gt_count for r in results)
    ac_mic_p, ac_mic_r, ac_mic_f1 = _prf(ac_c, ac_p, ac_g)

    fb_c = sum(r.feedback_metrics.matched_count for r in results)
    fb_p = sum(r.feedback_metrics.pred_count for r in results)
    fb_g = sum(r.feedback_metrics.gt_count for r in results)
    fb_mic_p, fb_mic_r, fb_mic_f1 = _prf(fb_c, fb_p, fb_g)

    in_c = sum(r.intent_metrics.matched_count for r in results)
    in_p = sum(r.intent_metrics.pred_count for r in results)
    in_g = sum(r.intent_metrics.gt_count for r in results)
    in_mic_p, in_mic_r, in_mic_f1 = _prf(in_c, in_p, in_g)

    micro_v4: dict[str, float | None] = {
        "presentation_scope_accuracy": psc,
        "screen_type_accuracy": stc,
        "outcome_state_type_accuracy": ost,
        "screen_enum_accuracy": screen_enum,
        "element_precision": el_mic_p,
        "element_recall": el_mic_r,
        "element_f1": el_mic_f1,
        "element_correct_count": float(el_c),
        "element_pred_count": float(el_p),
        "element_gt_count": float(el_g),
        "action_precision": ac_mic_p,
        "action_recall": ac_mic_r,
        "action_f1": ac_mic_f1,
        "action_correct_count": float(ac_c),
        "action_pred_count": float(ac_p),
        "action_gt_count": float(ac_g),
        "feedback_precision": fb_mic_p,
        "feedback_recall": fb_mic_r,
        "feedback_f1": fb_mic_f1,
        "feedback_correct_count": float(fb_c),
        "feedback_pred_count": float(fb_p),
        "feedback_gt_count": float(fb_g),
        "intent_precision": in_mic_p,
        "intent_recall": in_mic_r,
        "intent_f1": in_mic_f1,
        "intent_correct_count": float(in_c),
        "intent_pred_count": float(in_p),
        "intent_gt_count": float(in_g),
    }

    macro_v4: dict[str, float | None] = {
        "presentation_scope_accuracy": psc,
        "screen_type_accuracy": stc,
        "outcome_state_type_accuracy": ost,
        "screen_enum_accuracy": screen_enum,
        "element_precision": _mean([r.element_metrics.precision for r in results]),
        "element_recall": _mean([r.element_metrics.recall for r in results]),
        "element_f1": _mean([r.element_metrics.f1 for r in results]),
        "action_precision": _mean([r.action_metrics.precision for r in results]),
        "action_recall": _mean([r.action_metrics.recall for r in results]),
        "action_f1": _mean([r.action_metrics.f1 for r in results]),
        "feedback_precision": _mean([r.feedback_metrics.precision for r in results]),
        "feedback_recall": _mean([r.feedback_metrics.recall for r in results]),
        "feedback_f1": _mean([r.feedback_metrics.f1 for r in results]),
        "intent_precision": _mean([r.intent_metrics.precision for r in results]),
        "intent_recall": _mean([r.intent_metrics.recall for r in results]),
        "intent_f1": _mean([r.intent_metrics.f1 for r in results]),
    }

    return micro_v4, macro_v4, diagnostic
