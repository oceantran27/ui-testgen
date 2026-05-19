"""Greedy matching of prediction units to temp ground truth (spec §9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
    PredActionUnit,
    PredElementUnit,
    PredFeedbackUnit,
    PredGroupUnit,
    PredIntentUnit,
    PredictionEvaluationBundle,
)
from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
    ActionRecord,
    ElementRecord,
    ExpectedStepRecord,
    FeedbackRecord,
    GroupRecord,
    ScreenIntentRecord,
    TempGroundTruthDocument,
)
from experiments.ui_state_extraction.services.text_match_service import (
    longest_anchor_overlap_score,
    normalize_text_list,
    text_anchor_match,
)


def grounded_and_all_gt_element_ids(gt: TempGroundTruthDocument) -> tuple[set[str], set[str]]:
    """Text-grounded GT element ids (non-empty anchors after normalization) and all GT element ids."""
    all_ids: set[str] = set()
    grounded: set[str] = set()
    for e in gt.elements:
        all_ids.add(e.gt_element_id)
        if normalize_text_list(e.anchor_texts):
            grounded.add(e.gt_element_id)
    return grounded, all_ids


def _filter_empty_anchor_element_refs(
    ids: set[str],
    *,
    all_gt_el_ids: set[str],
    grounded_gt_el_ids: set[str],
) -> tuple[set[str], int]:
    """Drop GT element ids that are not text-grounded; return (filtered_set, excluded_count)."""
    out: set[str] = set()
    excluded = 0
    for x in ids:
        if x in all_gt_el_ids and x not in grounded_gt_el_ids:
            excluded += 1
            continue
        out.add(x)
    return out, excluded


def _gt_step_skipped_for_empty_anchor_element(
    gs_source_element_id: str | None,
    el_by_id: dict[str, ElementRecord],
) -> bool:
    if not gs_source_element_id:
        return False
    el = el_by_id.get(gs_source_element_id)
    if el is None:
        return False
    return not bool(normalize_text_list(el.anchor_texts))


def _action_grounding_correct(
    p: PredActionUnit,
    best: ActionRecord,
    el_map: dict[str, str],
) -> bool:
    """True when pred and GT agree on grounded element; no false positives from el_map.get default."""
    pg = (p.grounded_pred_element_id or "").strip() or None
    gg = best.grounded_element_id
    if not pg and not gg:
        return True
    if pg and pg not in el_map:
        return False
    mapped = el_map.get(pg) if pg else None
    if gg:
        return bool(pg) and mapped == gg
    return False


@dataclass
class UnitMatchResult:
    pred_to_gt_element: dict[str, str] = field(default_factory=dict)
    pred_to_gt_action: dict[str, str] = field(default_factory=dict)
    pred_to_gt_feedback: dict[str, str] = field(default_factory=dict)
    pred_to_gt_group: dict[str, str] = field(default_factory=dict)
    pred_intent_index_to_gt_intent: dict[int, ScreenIntentRecord] = field(default_factory=dict)

    element_rows: list[dict[str, Any]] = field(default_factory=list)
    action_rows: list[dict[str, Any]] = field(default_factory=list)
    feedback_rows: list[dict[str, Any]] = field(default_factory=list)
    group_rows: list[dict[str, Any]] = field(default_factory=list)
    intent_rows: list[dict[str, Any]] = field(default_factory=list)


def _tie_element(p: PredElementUnit, g: ElementRecord) -> tuple[int, int, int, int]:
    t = 1 if p.element_type == g.element_type else 0
    r = 1 if (p.role_hint or "") == (g.role_hint or "") else 0
    v = 1 if p.visual_region == g.visual_region else 0
    o = longest_anchor_overlap_score(p.anchor_texts, g.anchor_texts)
    return (t, r, v, o)


def match_elements(pred: PredictionEvaluationBundle, gt: TempGroundTruthDocument) -> UnitMatchResult:
    out = UnitMatchResult()
    used_gt: set[str] = set()
    for p in pred.elements:
        best: ElementRecord | None = None
        best_key: tuple[int, int, int, int] = (-1, -1, -1, -1)
        for g in gt.elements:
            if g.gt_element_id in used_gt:
                continue
            if not text_anchor_match(p.anchor_texts, g.anchor_texts):
                continue
            key = _tie_element(p, g)
            if key > best_key:
                best_key = key
                best = g
        if best is not None:
            used_gt.add(best.gt_element_id)
            out.pred_to_gt_element[p.pred_element_id] = best.gt_element_id
            match_reason = "anchor_match"
            out.element_rows.append(
                {
                    "pred_element_id": p.pred_element_id,
                    "gt_element_id": best.gt_element_id,
                    "match_reason": match_reason,
                    "pred_anchor_texts": p.anchor_texts,
                    "gt_anchor_texts": best.anchor_texts,
                    "element_type_correct": p.element_type == best.element_type,
                    "role_hint_correct": (p.role_hint or "") == (best.role_hint or ""),
                    "visual_region_correct": p.visual_region == best.visual_region,
                }
            )
        else:
            out.element_rows.append(
                {
                    "pred_element_id": p.pred_element_id,
                    "gt_element_id": None,
                    "match_reason": "no_match",
                    "pred_anchor_texts": p.anchor_texts,
                    "gt_anchor_texts": [],
                }
            )
    return out


def _grounded_element_ok(p: PredActionUnit, g: ActionRecord, el_map: dict[str, str]) -> bool:
    if not p.grounded_pred_element_id or not g.grounded_element_id:
        return False
    return el_map.get(p.grounded_pred_element_id) == g.grounded_element_id


def _tie_action(
    p: PredActionUnit,
    g: ActionRecord,
    el_map: dict[str, str],
) -> tuple[int, int, int, int]:
    t = 1 if p.action_type == g.action_type else 0
    gr = 1 if _grounded_element_ok(p, g, el_map) else 0
    a = 1 if text_anchor_match(p.anchor_texts, g.anchor_texts) else 0
    v = 1 if p.visual_region == g.visual_region else 0
    return (t, gr, a, v)


def match_actions(
    pred: PredictionEvaluationBundle,
    gt: TempGroundTruthDocument,
    el_map: dict[str, str],
    partial: UnitMatchResult,
) -> None:
    used_gt: set[str] = set()
    for p in pred.actions:
        best: ActionRecord | None = None
        best_key = (-1, -1, -1, -1)
        anchor_ok = False
        grounded_ok = False
        for g in gt.actions:
            if g.gt_action_id in used_gt:
                continue
            t_anchor = text_anchor_match(p.anchor_texts, g.anchor_texts)
            t_gr = _grounded_element_ok(p, g, el_map)
            if not t_anchor and not t_gr:
                continue
            key = _tie_action(p, g, el_map)
            if key > best_key:
                best_key = key
                best = g
                anchor_ok = t_anchor
                grounded_ok = t_gr
        if best is not None:
            used_gt.add(best.gt_action_id)
            partial.pred_to_gt_action[p.pred_action_id] = best.gt_action_id
            reason = "grounded_element_match" if grounded_ok and not anchor_ok else "anchor_match"
            if grounded_ok and anchor_ok:
                reason = "anchor_and_grounded"
            partial.action_rows.append(
                {
                    "pred_action_id": p.pred_action_id,
                    "gt_action_id": best.gt_action_id,
                    "match_reason": reason,
                    "pred_anchor_texts": p.anchor_texts,
                    "gt_anchor_texts": best.anchor_texts,
                    "action_type_correct": p.action_type == best.action_type,
                    "grounding_correct": _action_grounding_correct(p, best, el_map),
                }
            )
        else:
            partial.action_rows.append(
                {
                    "pred_action_id": p.pred_action_id,
                    "gt_action_id": None,
                    "match_reason": "no_match",
                    "pred_anchor_texts": p.anchor_texts,
                    "gt_anchor_texts": [],
                }
            )


def _mapped_related_elements(
    pred_ids: list[str],
    el_map: dict[str, str],
) -> set[str]:
    return {el_map[x] for x in pred_ids if x in el_map}


def match_feedback(
    pred: PredictionEvaluationBundle,
    gt: TempGroundTruthDocument,
    el_map: dict[str, str],
    partial: UnitMatchResult,
    *,
    grounded_gt_el_ids: set[str],
    all_gt_el_ids: set[str],
) -> None:
    used_gt: set[str] = set()
    for p in pred.feedback:
        best: FeedbackRecord | None = None
        for g in gt.feedback:
            if g.gt_feedback_id in used_gt:
                continue
            if text_anchor_match(p.anchor_texts, g.anchor_texts):
                best = g
                break
        if best is not None:
            used_gt.add(best.gt_feedback_id)
            partial.pred_to_gt_feedback[p.pred_feedback_id] = best.gt_feedback_id
            pred_rel = _mapped_related_elements(p.related_pred_element_ids, el_map)
            gt_rel = set(best.related_element_ids)
            pred_eff, pred_excl = _filter_empty_anchor_element_refs(
                pred_rel,
                all_gt_el_ids=all_gt_el_ids,
                grounded_gt_el_ids=grounded_gt_el_ids,
            )
            gt_eff, gt_excl = _filter_empty_anchor_element_refs(
                gt_rel,
                all_gt_el_ids=all_gt_el_ids,
                grounded_gt_el_ids=grounded_gt_el_ids,
            )
            rel_ok = pred_eff == gt_eff if pred_eff or gt_eff else True
            partial.feedback_rows.append(
                {
                    "pred_feedback_id": p.pred_feedback_id,
                    "gt_feedback_id": best.gt_feedback_id,
                    "match_reason": "anchor_match",
                    "pred_anchor_texts": p.anchor_texts,
                    "gt_anchor_texts": best.anchor_texts,
                    "feedback_type_correct": p.feedback_type == best.feedback_type,
                    "related_elements_correct": rel_ok,
                    "related_empty_anchor_excluded_pred": pred_excl,
                    "related_empty_anchor_excluded_gt": gt_excl,
                }
            )
        else:
            partial.feedback_rows.append(
                {
                    "pred_feedback_id": p.pred_feedback_id,
                    "gt_feedback_id": None,
                    "match_reason": "no_match",
                    "pred_anchor_texts": p.anchor_texts,
                    "gt_anchor_texts": [],
                }
            )


def _member_gt_set(
    group: PredGroupUnit,
    el_m: dict[str, str],
    ac_m: dict[str, str],
    fb_m: dict[str, str],
) -> set[str]:
    s: set[str] = set()
    for x in group.member_pred_element_ids:
        if x in el_m:
            s.add(el_m[x])
    for x in group.member_pred_action_ids:
        if x in ac_m:
            s.add(ac_m[x])
    for x in group.member_pred_feedback_ids:
        if x in fb_m:
            s.add(fb_m[x])
    return s


def _group_member_gt_set(g: GroupRecord) -> set[str]:
    return set(g.member_element_ids) | set(g.member_action_ids) | set(g.member_feedback_ids)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    uni = len(a | b)
    return inter / uni if uni else 0.0


def _membership_prf(pred_s: set[str], gt_s: set[str]) -> tuple[float, float, float]:
    if not pred_s and not gt_s:
        return 1.0, 1.0, 1.0
    inter = pred_s & gt_s
    if not pred_s:
        p = 0.0
    else:
        p = len(inter) / len(pred_s)
    if not gt_s:
        r = 0.0
    else:
        r = len(inter) / len(gt_s)
    if p + r == 0:
        return p, r, 0.0
    f1 = 2 * p * r / (p + r)
    return p, r, f1


def match_groups(
    pred: PredictionEvaluationBundle,
    gt: TempGroundTruthDocument,
    el_m: dict[str, str],
    ac_m: dict[str, str],
    fb_m: dict[str, str],
    partial: UnitMatchResult,
    *,
    threshold: float,
    grounded_gt_el_ids: set[str],
    all_gt_el_ids: set[str],
) -> None:
    used_gt: set[str] = set()
    for pg in pred.groups:
        pred_s_full = _member_gt_set(pg, el_m, ac_m, fb_m)
        pred_s, pred_excl = _filter_empty_anchor_element_refs(
            pred_s_full,
            all_gt_el_ids=all_gt_el_ids,
            grounded_gt_el_ids=grounded_gt_el_ids,
        )
        best: GroupRecord | None = None
        best_j = -1.0
        for gg in gt.groups:
            if gg.gt_group_id in used_gt:
                continue
            gt_s_full = _group_member_gt_set(gg)
            gt_s_cand, _gt_ex_cand = _filter_empty_anchor_element_refs(
                gt_s_full,
                all_gt_el_ids=all_gt_el_ids,
                grounded_gt_el_ids=grounded_gt_el_ids,
            )
            j = _jaccard(pred_s, gt_s_cand)
            if j >= threshold and j > best_j:
                best_j = j
                best = gg
        if best is not None:
            used_gt.add(best.gt_group_id)
            partial.pred_to_gt_group[pg.pred_group_id] = best.gt_group_id
            gt_s_full = _group_member_gt_set(best)
            gt_s, gt_excl = _filter_empty_anchor_element_refs(
                gt_s_full,
                all_gt_el_ids=all_gt_el_ids,
                grounded_gt_el_ids=grounded_gt_el_ids,
            )
            mp, mr, mf1 = _membership_prf(pred_s, gt_s)
            prim_ok = False
            if pg.primary_pred_action_id and best.primary_action_id:
                prim_ok = ac_m.get(pg.primary_pred_action_id) == best.primary_action_id
            elif not pg.primary_pred_action_id and not best.primary_action_id:
                prim_ok = True
            partial.group_rows.append(
                {
                    "pred_group_id": pg.pred_group_id,
                    "gt_group_id": best.gt_group_id,
                    "jaccard": best_j,
                    "membership_precision": mp,
                    "membership_recall": mr,
                    "membership_f1": mf1,
                    "group_type_correct": pg.group_type == best.group_type,
                    "primary_action_correct": prim_ok,
                    "membership_empty_anchor_excluded_pred": pred_excl,
                    "membership_empty_anchor_excluded_gt": gt_excl,
                }
            )
        else:
            partial.group_rows.append(
                {
                    "pred_group_id": pg.pred_group_id,
                    "gt_group_id": None,
                    "jaccard": 0.0,
                    "membership_precision": 0.0,
                    "membership_recall": 0.0,
                    "membership_f1": 0.0,
                    "membership_empty_anchor_excluded_pred": pred_excl,
                    "membership_empty_anchor_excluded_gt": 0,
                }
            )


def _intent_pair_ok(
    p: PredIntentUnit,
    g: ScreenIntentRecord,
    ig_m: dict[str, str],
    ac_m: dict[str, str],
) -> bool:
    if p.intent_kind != g.intent_kind:
        return False
    pm = ac_m.get(p.primary_pred_action_id) if p.primary_pred_action_id else None
    cm = ac_m.get(p.commit_pred_action_id) if p.commit_pred_action_id else None
    gt_actions = {g.primary_action_id, g.commit_action_id} - {None}
    pred_mapped = {x for x in (pm, cm) if x}
    if pred_mapped & gt_actions:
        return True
    # fallback: no actionable ids on both sides → source group
    if not pred_mapped and not gt_actions:
        sg = ig_m.get(p.source_pred_group_id)
        return bool(sg and sg == g.source_group_id)
    if not g.primary_action_id and not g.commit_action_id:
        sg = ig_m.get(p.source_pred_group_id)
        return bool(sg and sg == g.source_group_id)
    return False


def match_intents(
    pred: PredictionEvaluationBundle,
    gt: TempGroundTruthDocument,
    ig_m: dict[str, str],
    ac_m: dict[str, str],
    partial: UnitMatchResult,
) -> None:
    used: set[str] = set()
    for p in pred.intents:
        best: ScreenIntentRecord | None = None
        for g in gt.screen_intents:
            if g.gt_intent_id in used:
                continue
            if _intent_pair_ok(p, g, ig_m, ac_m):
                best = g
                break
        if best is not None:
            used.add(best.gt_intent_id)
            partial.pred_intent_index_to_gt_intent[p.pred_intent_index] = best
            pm = ac_m.get(p.primary_pred_action_id) if p.primary_pred_action_id else None
            cm = ac_m.get(p.commit_pred_action_id) if p.commit_pred_action_id else None
            reason = "intent_kind_and_commit_action"
            if cm and cm == best.commit_action_id:
                reason = "intent_kind_and_commit_action"
            elif pm and pm == best.primary_action_id:
                reason = "intent_kind_and_primary_action"
            else:
                reason = "intent_kind_and_source_group_fallback"
            partial.intent_rows.append(
                {
                    "pred_intent_index": p.pred_intent_index,
                    "gt_intent_id": best.gt_intent_id,
                    "match_reason": reason,
                    "intent_kind_correct": True,
                    "commit_action_correct": bool(cm and cm == best.commit_action_id),
                    "primary_action_correct": bool(pm and pm == best.primary_action_id),
                }
            )
        else:
            partial.intent_rows.append(
                {
                    "pred_intent_index": p.pred_intent_index,
                    "gt_intent_id": None,
                    "match_reason": "no_match",
                    "intent_kind_correct": False,
                }
            )


def match_all_units(
    pred: PredictionEvaluationBundle,
    gt: TempGroundTruthDocument,
    *,
    group_jaccard_threshold: float,
) -> UnitMatchResult:
    grounded_gt_el_ids, all_gt_el_ids = grounded_and_all_gt_element_ids(gt)
    el_part = match_elements(pred, gt)
    match_actions(pred, gt, el_part.pred_to_gt_element, el_part)
    match_feedback(
        pred,
        gt,
        el_part.pred_to_gt_element,
        el_part,
        grounded_gt_el_ids=grounded_gt_el_ids,
        all_gt_el_ids=all_gt_el_ids,
    )
    match_groups(
        pred,
        gt,
        el_part.pred_to_gt_element,
        el_part.pred_to_gt_action,
        el_part.pred_to_gt_feedback,
        el_part,
        threshold=group_jaccard_threshold,
        grounded_gt_el_ids=grounded_gt_el_ids,
        all_gt_el_ids=all_gt_el_ids,
    )
    match_intents(pred, gt, el_part.pred_to_gt_group, el_part.pred_to_gt_action, el_part)
    return el_part


def map_raw_evidence_to_gt(
    source_id: str,
    el_m: dict[str, str],
    ac_m: dict[str, str],
    fb_m: dict[str, str],
    ig_m: dict[str, str],
) -> str | None:
    if source_id in ac_m:
        return ac_m[source_id]
    if source_id in el_m:
        return el_m[source_id]
    if source_id in fb_m:
        return fb_m[source_id]
    if source_id in ig_m:
        return ig_m[source_id]
    return None


def set_f1(pred_set: set[str], gt_set: set[str]) -> tuple[float | None, float | None, float | None]:
    if not pred_set and not gt_set:
        return None, None, None
    inter = pred_set & gt_set
    if not pred_set:
        p: float | None = None
    else:
        p = len(inter) / len(pred_set)
    if not gt_set:
        r = None
    else:
        r = len(inter) / len(gt_set)
    if p is None or r is None:
        return p, r, None
    if p + r == 0:
        return p, r, 0.0
    return p, r, 2 * p * r / (p + r)


def required_input_mapping_explain(
    p: PredIntentUnit,
    g: ScreenIntentRecord,
    el_m: dict[str, str],
    gt_doc: TempGroundTruthDocument,
) -> dict[str, Any]:
    """Debug: raw required element ids vs mapped GT ids after element match (el_m)."""
    grounded_gt_el_ids, all_gt_el_ids = grounded_and_all_gt_element_ids(gt_doc)
    pred_raw = [str(x) for x in p.required_pred_element_ids]
    dropped_pred_ids = [x for x in pred_raw if x not in el_m]
    mapped_gt_ids = sorted({el_m[x] for x in pred_raw if x in el_m})
    gt_required_ids = sorted(set(g.required_input_element_ids))
    pred_req_set = {el_m[x] for x in pred_raw if x in el_m}
    gt_req_set = set(g.required_input_element_ids)
    pred_eff, _pred_ex = _filter_empty_anchor_element_refs(
        pred_req_set,
        all_gt_el_ids=all_gt_el_ids,
        grounded_gt_el_ids=grounded_gt_el_ids,
    )
    gt_eff, _gt_ex = _filter_empty_anchor_element_refs(
        gt_req_set,
        all_gt_el_ids=all_gt_el_ids,
        grounded_gt_el_ids=grounded_gt_el_ids,
    )
    _rq_p, _rq_r, rq_f1 = set_f1(pred_eff, gt_eff)
    return {
        "pred_intent_index": p.pred_intent_index,
        "gt_intent_id": g.gt_intent_id,
        "pred_raw_ids": pred_raw,
        "mapped_gt_ids": mapped_gt_ids,
        "gt_required_ids": gt_required_ids,
        "dropped_pred_ids": dropped_pred_ids,
        "required_input_f1": rq_f1,
    }


def compute_intent_field_metrics(
    p: PredIntentUnit,
    g: ScreenIntentRecord,
    el_m: dict[str, str],
    ac_m: dict[str, str],
    fb_m: dict[str, str],
    ig_m: dict[str, str],
    gt_doc: TempGroundTruthDocument,
) -> dict[str, Any]:
    """Set-F1 and bool accuracies for a matched intent pair."""
    grounded_gt_el_ids, all_gt_el_ids = grounded_and_all_gt_element_ids(gt_doc)
    el_by_id = {e.gt_element_id: e for e in gt_doc.elements}

    pred_sec = {ac_m[x] for x in p.secondary_pred_action_ids if x in ac_m}
    gt_sec = set(g.secondary_action_ids)
    sp, sr, sf1 = set_f1(pred_sec, gt_sec)

    pred_req = {el_m[x] for x in p.required_pred_element_ids if x in el_m}
    gt_req = set(g.required_input_element_ids)
    pred_req_eff, pred_req_excl = _filter_empty_anchor_element_refs(
        pred_req,
        all_gt_el_ids=all_gt_el_ids,
        grounded_gt_el_ids=grounded_gt_el_ids,
    )
    gt_req_eff, gt_req_excl = _filter_empty_anchor_element_refs(
        gt_req,
        all_gt_el_ids=all_gt_el_ids,
        grounded_gt_el_ids=grounded_gt_el_ids,
    )
    rq_p, rq_r, rq_f1 = set_f1(pred_req_eff, gt_req_eff)

    pred_evid: set[str] = set()
    for sid in p.evidence_pred_target_ids:
        mid = map_raw_evidence_to_gt(sid, el_m, ac_m, fb_m, ig_m)
        if mid:
            pred_evid.add(mid)
    gt_evid = set(g.evidence_target_ids)
    pred_evid_eff, pred_evid_excl = _filter_empty_anchor_element_refs(
        pred_evid,
        all_gt_el_ids=all_gt_el_ids,
        grounded_gt_el_ids=grounded_gt_el_ids,
    )
    gt_evid_eff, gt_evid_excl = _filter_empty_anchor_element_refs(
        gt_evid,
        all_gt_el_ids=all_gt_el_ids,
        grounded_gt_el_ids=grounded_gt_el_ids,
    )
    ev_p, ev_r, ev_f1 = set_f1(pred_evid_eff, gt_evid_eff)

    gt_steps_eff: list[ExpectedStepRecord] = []
    steps_excluded_empty_anchor = 0
    for gs in g.expected_steps:
        if _gt_step_skipped_for_empty_anchor_element(gs.source_element_id, el_by_id):
            steps_excluded_empty_anchor += 1
            continue
        gt_steps_eff.append(gs)

    steps_total = 0
    steps_ok = 0
    for i, ps in enumerate(p.expected_steps):
        if i >= len(gt_steps_eff):
            break
        gs = gt_steps_eff[i]
        steps_total += 1
        pa = ac_m.get(ps.source_pred_action_id or "") if ps.source_pred_action_id else None
        pe = el_m.get(ps.source_pred_element_id or "") if ps.source_pred_element_id else None
        ok_a = (pa is None and gs.source_action_id is None) or (pa == gs.source_action_id)
        ok_e = (pe is None and gs.source_element_id is None) or (pe == gs.source_element_id)
        if ok_a and ok_e:
            steps_ok += 1
    step_acc = steps_ok / steps_total if steps_total else None

    return {
        "source_group_ok": ig_m.get(p.source_pred_group_id) == g.source_group_id,
        "primary_ok": ac_m.get(p.primary_pred_action_id or "") == g.primary_action_id
        if p.primary_pred_action_id and g.primary_action_id
        else (not p.primary_pred_action_id and not g.primary_action_id),
        "commit_ok": ac_m.get(p.commit_pred_action_id or "") == g.commit_action_id
        if p.commit_pred_action_id and g.commit_action_id
        else True,
        "secondary_precision": sp,
        "secondary_recall": sr,
        "secondary_f1": sf1,
        "required_input_precision": rq_p,
        "required_input_recall": rq_r,
        "required_input_f1": rq_f1,
        "required_input_empty_anchor_excluded_pred_refs": pred_req_excl,
        "required_input_empty_anchor_excluded_gt_refs": gt_req_excl,
        "evidence_precision": ev_p,
        "evidence_recall": ev_r,
        "evidence_f1": ev_f1,
        "evidence_empty_anchor_excluded_pred_refs": pred_evid_excl,
        "evidence_empty_anchor_excluded_gt_refs": gt_evid_excl,
        "step_grounding_accuracy": step_acc,
        "steps_correct": steps_ok,
        "steps_total": steps_total,
        "step_empty_anchor_excluded_count": steps_excluded_empty_anchor,
    }
