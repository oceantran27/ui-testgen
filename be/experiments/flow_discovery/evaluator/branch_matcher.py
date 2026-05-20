"""Compare predicted branch clusters to reviewed ``GroundTruthBranchGroup`` rows."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from experiments.flow_discovery.schemas.evaluation_schema import BranchEvalItem
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage


def _outcome_set_for_gt_group(pkg: GroundTruthFlowPackage, alternative_transition_ids: List[str]) -> Set[Tuple[str, str]]:
    out: Set[Tuple[str, str]] = set()
    alt_set = set(alternative_transition_ids or [])
    for t in pkg.transitions:
        if t.gt_transition_id not in alt_set:
            continue
        out.add((str(t.outcome_type or "").strip().lower(), t.to_state_id))
    return out


def _rows_for_pred_group(
    predicted_rows: List[Dict[str, Any]],
    pred_transition_ids: List[str],
) -> List[Dict[str, Any]]:
    wanted = set(pred_transition_ids or [])
    return [r for r in predicted_rows if str(r.get("pred_transition_id") or "") in wanted]


def _pred_outcome_set(rows: List[Dict[str, Any]]) -> Set[Tuple[str, str]]:
    return {
        (str(r.get("outcome_type") or "").strip().lower(), str(r.get("to_state_id") or ""))
        for r in rows
    }


def evaluate_branches(
    pkg: GroundTruthFlowPackage,
    predicted_rows: List[Dict[str, Any]],
    predicted_branch_groups: List[Dict[str, Any]],
) -> Tuple[List[BranchEvalItem], float, float, float]:
    """Return branch items and macro precision/recall/F1 over evaluable groups."""

    pred_by_key: Dict[str, Dict[str, Any]] = {}
    for pg in predicted_branch_groups:
        key = f"{pg.get('anchor_source_gt_state_id') or ''}||{pg.get('normalized_trigger') or ''}"
        pred_by_key[key] = pg

    items: List[BranchEvalItem] = []
    precs: List[float] = []
    recs: List[float] = []
    f1s: List[float] = []

    for bg in pkg.branch_groups:
        if not getattr(bg, "eval_include", True):
            continue
        key = f"{bg.anchor_source_gt_state_id}||{bg.normalized_trigger}"
        gt_set = _outcome_set_for_gt_group(pkg, list(bg.alternative_transition_ids or []))
        if len(gt_set) < 2:
            continue

        pg = pred_by_key.get(key)
        if not pg:
            items.append(
                BranchEvalItem(
                    branch_key=key,
                    gt_branch_group_id=bg.branch_group_id,
                    match_status="false_negative",
                    error_tags=["missing_branch"],
                ),
            )
            precs.append(0.0)
            recs.append(0.0)
            f1s.append(0.0)
            continue

        pr_rows = _rows_for_pred_group(predicted_rows, list(pg.get("pred_transition_ids") or []))
        pr_set = _pred_outcome_set(pr_rows)
        inter = gt_set & pr_set
        prec = len(inter) / len(pr_set) if pr_set else (1.0 if not gt_set else 0.0)
        rec = len(inter) / len(gt_set) if gt_set else (1.0 if not pr_set else 0.0)
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        precs.append(prec)
        recs.append(rec)
        f1s.append(f1)

        err: List[str] = []
        if pr_set - gt_set:
            err.append("extra_branch")
        if gt_set - pr_set:
            err.append("missing_branch")

        items.append(
            BranchEvalItem(
                branch_key=key,
                gt_branch_group_id=bg.branch_group_id,
                pred_semantic_cluster_id=str(pg.get("pred_branch_id") or ""),
                match_status="evaluated",
                error_tags=err,
            ),
        )

    macro_p = sum(precs) / len(precs) if precs else 1.0
    macro_r = sum(recs) / len(recs) if recs else 1.0
    macro_f1 = sum(f1s) / len(f1s) if f1s else 1.0
    return items, macro_p, macro_r, macro_f1
