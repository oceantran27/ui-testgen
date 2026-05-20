"""Greedy matching of prediction units to temp ground truth (spec §9)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
    PredActionUnit,
    PredElementUnit,
    PredExpectedStepUnit,
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
from experiments.ui_state_extraction.services.evaluation_key_service import has_evaluable_key
from experiments.ui_state_extraction.services.key_metric_service import counter_prf
from experiments.ui_state_extraction.services.text_match_service import (
    longest_anchor_overlap_score,
    text_anchor_match,
)

# Prediction refs that do not resolve through unit maps appear as sentinel tokens so
# micro precision/recall count hallucinated / unmatched references.
UNMAPPED_ELEMENT_PREFIX = "UNMAPPED_ELEMENT::"
UNMAPPED_EVIDENCE_PREFIX = "UNMAPPED_EVIDENCE::"
UNMAPPED_ACTION_PREFIX = "UNMAPPED_ACTION::"


def _safe_div_micro(num: float, den: int) -> float | None:
    if den == 0:
        return None
    return num / den


def _prf_from_counts(matched: int, pred_n: int, gt_n: int) -> tuple[float | None, float | None, float | None]:
    prec = _safe_div_micro(float(matched), pred_n) if pred_n else None
    rec = _safe_div_micro(float(matched), gt_n) if gt_n else None
    if prec is None or rec is None:
        return prec, rec, None
    if prec + rec == 0:
        return prec, rec, 0.0
    return prec, rec, 2 * prec * rec / (prec + rec)


def map_pred_element_ref(raw_id: str, el_m: dict[str, str]) -> str:
    rid = (raw_id or "").strip()
    if not rid:
        return rid
    return el_m.get(rid) or f"{UNMAPPED_ELEMENT_PREFIX}{rid}"


def map_pred_evidence_ref(
    raw_id: str,
    el_m: dict[str, str],
    ac_m: dict[str, str],
    fb_m: dict[str, str],
    ig_m: dict[str, str],
) -> str:
    rid = (raw_id or "").strip()
    if not rid:
        return rid
    mid = map_raw_evidence_to_gt(rid, el_m, ac_m, fb_m, ig_m)
    return mid if mid else f"{UNMAPPED_EVIDENCE_PREFIX}{rid}"


def canonical_step_type(step_type: str) -> str:
    t = (step_type or "").strip().lower()
    if t == "tap":
        return "invoke_action"
    return t


StepKey = tuple[str, str | None, str | None]


def _gt_step_key(gs: ExpectedStepRecord) -> StepKey:
    return (
        canonical_step_type(gs.step_type),
        gs.source_action_id,
        gs.source_element_id,
    )


def _pred_step_key(ps: PredExpectedStepUnit, ac_m: dict[str, str], el_m: dict[str, str]) -> StepKey:
    st = canonical_step_type(ps.step_type)
    ra = (ps.source_pred_action_id or "").strip()
    re = (ps.source_pred_element_id or "").strip()
    mapped_action: str | None = None
    if ra:
        mapped_action = ac_m.get(ra) or f"{UNMAPPED_ACTION_PREFIX}{ra}"
    mapped_el: str | None = None
    if re:
        mapped_el = el_m.get(re) or f"{UNMAPPED_ELEMENT_PREFIX}{re}"
    return st, mapped_action, mapped_el


def multiset_step_prf(pred_counter: Counter[StepKey], gt_counter: Counter[StepKey]) -> dict[str, Any]:
    core = counter_prf(pred_counter, gt_counter)
    matched = core.correct_count
    precision, recall, f1 = core.precision, core.recall, core.f1
    extra = core.extra
    missing = core.missing

    def _expand(cnt: Counter[StepKey]) -> list[list[str | None]]:
        out: list[list[str | None]] = []
        for k, mult in cnt.items():
            row: list[str | None] = [k[0], k[1], k[2]]
            for _ in range(mult):
                out.append(row)
        return out

    return {
        "correct_count": matched,
        "pred_count": core.pred_count,
        "gt_count": core.gt_count,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "extra_steps": _expand(extra),
        "missing_steps": _expand(missing),
    }


def counter_step_keys_as_lists(cnt: Counter[StepKey]) -> list[list[str | None]]:
    """Multiset keys serialized for JSON (repeat rows for multiplicity); keys sorted lexicographically."""
    out: list[list[str | None]] = []
    for k in sorted(cnt.keys(), key=lambda t: (t[0], t[1] or "", t[2] or "")):
        row = [k[0], k[1], k[2]]
        for _ in range(cnt[k]):
            out.append(list(row))
    return out


def grounded_and_all_gt_element_ids(gt: TempGroundTruthDocument) -> tuple[set[str], set[str]]:
    """Text-grounded GT element ids (evaluable element key) and all GT element ids."""
    all_ids: set[str] = set()
    grounded: set[str] = set()
    for e in gt.elements:
        all_ids.add(e.gt_element_id)
        if has_evaluable_key(e, kind="element"):
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
    return not has_evaluable_key(el, kind="element")


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


def set_eff_metrics(pred_eff: set[str], gt_eff: set[str]) -> dict[str, Any]:
    """P/R/F1 and counts after empty-anchor filtering. Both empty sets → no metric (N/A)."""
    if not pred_eff and not gt_eff:
        return {
            "correct_count": 0,
            "pred_count": 0,
            "gt_count": 0,
            "precision": None,
            "recall": None,
            "f1": None,
        }
    inter = pred_eff & gt_eff
    c = len(inter)
    p_n = len(pred_eff)
    g_n = len(gt_eff)
    prec, rec, f1 = _prf_from_counts(c, p_n, g_n)
    return {
        "correct_count": c,
        "pred_count": p_n,
        "gt_count": g_n,
        "precision": prec,
        "recall": rec,
        "f1": f1,
    }


def set_f1(pred_set: set[str], gt_set: set[str]) -> tuple[float | None, float | None, float | None]:
    m = set_eff_metrics(pred_set, gt_set)
    return m["precision"], m["recall"], m["f1"]


def required_input_mapping_explain(
    p: PredIntentUnit,
    g: ScreenIntentRecord,
    el_m: dict[str, str],
    gt_doc: TempGroundTruthDocument,
) -> dict[str, Any]:
    """Debug: raw required element ids vs mapped GT ids after element match (el_m)."""
    grounded_gt_el_ids, all_gt_el_ids = grounded_and_all_gt_element_ids(gt_doc)
    pred_raw = [str(x) for x in p.required_pred_element_ids if x and str(x).strip()]
    pred_req_set = {map_pred_element_ref(x, el_m) for x in pred_raw}
    unmapped_pred_ids = [x for x in pred_raw if not el_m.get(x)]

    gt_required_ids = sorted(set(g.required_input_element_ids))
    mapped_gt_no_unmapped = sorted({map_pred_element_ref(x, el_m) for x in pred_raw if el_m.get(x)})

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
    rq = set_eff_metrics(pred_eff, gt_eff)

    pred_effective_sorted = sorted(pred_eff)

    return {
        "pred_intent_index": p.pred_intent_index,
        "gt_intent_id": g.gt_intent_id,
        "pred_raw_ids": pred_raw,
        # GT ids reachable from preds that mapped through el_m (excluding UNMAPPED tokens)
        "mapped_gt_ids": mapped_gt_no_unmapped,
        "gt_required_ids": gt_required_ids,
        "unmapped_pred_ids": unmapped_pred_ids,
        "pred_effective_ids": pred_effective_sorted,
        "required_input_correct_count": rq["correct_count"],
        "required_input_pred_count": rq["pred_count"],
        "required_input_gt_count": rq["gt_count"],
        "required_input_precision": rq["precision"],
        "required_input_recall": rq["recall"],
        "required_input_f1": rq["f1"],
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

    pred_raw_req = [
        str(x) for x in p.required_pred_element_ids if x and str(x).strip()
    ]
    pred_req = {map_pred_element_ref(x, el_m) for x in pred_raw_req}
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
    rq_met = set_eff_metrics(pred_req_eff, gt_req_eff)
    rq_p, rq_r, rq_f1 = rq_met["precision"], rq_met["recall"], rq_met["f1"]

    pred_evid_raw = [
        str(sid) for sid in p.evidence_pred_target_ids if sid and str(sid).strip()
    ]
    pred_evid = {map_pred_evidence_ref(sid, el_m, ac_m, fb_m, ig_m) for sid in pred_evid_raw}
    pred_evid.discard("")  # empty map_evidence refs already skipped
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
    ev_met = set_eff_metrics(pred_evid_eff, gt_evid_eff)
    ev_p, ev_r, ev_f1 = ev_met["precision"], ev_met["recall"], ev_met["f1"]

    gt_steps_eff: list[ExpectedStepRecord] = []
    steps_excluded_empty_anchor = 0
    for gs in g.expected_steps:
        if _gt_step_skipped_for_empty_anchor_element(gs.source_element_id, el_by_id):
            steps_excluded_empty_anchor += 1
            continue
        gt_steps_eff.append(gs)

    pred_ctr: Counter[StepKey] = Counter()
    for ps in p.expected_steps:
        pred_ctr[_pred_step_key(ps, ac_m, el_m)] += 1
    gt_ctr: Counter[StepKey] = Counter()
    for gs in gt_steps_eff:
        gt_ctr[_gt_step_key(gs)] += 1
    step_met = multiset_step_prf(pred_ctr, gt_ctr)
    pred_step_keys_dbg = counter_step_keys_as_lists(pred_ctr)
    gt_step_keys_dbg = counter_step_keys_as_lists(gt_ctr)

    step_debug = {
        "pred_step_keys": pred_step_keys_dbg,
        "gt_step_keys": gt_step_keys_dbg,
        "matched_count": step_met["correct_count"],
        "pred_count": step_met["pred_count"],
        "gt_count": step_met["gt_count"],
        "missing_steps": step_met["missing_steps"],
        "extra_steps": step_met["extra_steps"],
        "empty_anchor_excluded_count": steps_excluded_empty_anchor,
    }

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
        "required_input_correct_count": rq_met["correct_count"],
        "required_input_pred_count": rq_met["pred_count"],
        "required_input_gt_count": rq_met["gt_count"],
        "required_input_precision": rq_p,
        "required_input_recall": rq_r,
        "required_input_f1": rq_f1,
        "required_input_empty_anchor_excluded_pred_refs": pred_req_excl,
        "required_input_empty_anchor_excluded_gt_refs": gt_req_excl,
        "evidence_precision": ev_p,
        "evidence_recall": ev_r,
        "evidence_f1": ev_f1,
        "evidence_target_correct_count": ev_met["correct_count"],
        "evidence_target_pred_count": ev_met["pred_count"],
        "evidence_target_gt_count": ev_met["gt_count"],
        "evidence_target_precision": ev_p,
        "evidence_target_recall": ev_r,
        "evidence_target_f1": ev_f1,
        "evidence_empty_anchor_excluded_pred_refs": pred_evid_excl,
        "evidence_empty_anchor_excluded_gt_refs": gt_evid_excl,
        "step_correct_count": step_met["correct_count"],
        "step_pred_count": step_met["pred_count"],
        "step_gt_count": step_met["gt_count"],
        "step_precision": step_met["precision"],
        "step_recall": step_met["recall"],
        "step_f1": step_met["f1"],
        "step_grounding_accuracy": step_met["f1"],
        "step_empty_anchor_excluded_count": steps_excluded_empty_anchor,
        "step_missing_steps": step_met["missing_steps"],
        "step_extra_steps": step_met["extra_steps"],
        "step_debug": step_debug,
        "steps_correct": step_met["correct_count"],
        "steps_total": step_met["pred_count"],
    }
