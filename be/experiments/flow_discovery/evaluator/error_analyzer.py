"""Tag and count error categories for thesis-style breakdown tables."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Set

from experiments.flow_discovery.evaluator.transition_matcher import TransitionMatchBundle
from experiments.flow_discovery.schemas.evaluation_schema import BranchEvalItem, FlowEvalItem, TransitionMatchItem


def analyze_errors(
    bundle: TransitionMatchBundle,
    flow_items: List[FlowEvalItem],
    branch_items: List[BranchEvalItem],
    *,
    invalid_transition_tags: List[str],
) -> Dict[str, int]:
    c: Counter[str] = Counter()

    def _count_item_tags(items: List[TransitionMatchItem]) -> None:
        for it in items:
            for tag in it.error_tags:
                c[tag] += 1

    _count_item_tags(bundle.strict_items)
    _count_item_tags(bundle.false_negatives_strict)
    for it in flow_items:
        for tag in it.error_tags:
            c[tag] += 1
    for it in branch_items:
        for tag in it.error_tags:
            c[tag] += 1
    for tag in invalid_transition_tags:
        c[tag] += 1

    for it in bundle.strict_items:
        if it.match_status == "false_positive":
            c["false_positive_strict"] += 1
    for it in bundle.false_negatives_strict:
        if it.match_status == "false_negative":
            c["false_negative_strict"] += 1

    return dict(sorted(c.items(), key=lambda x: -x[1]))


def invalid_pred_references(
    predicted_rows: List[Dict[str, Any]],
    gt_state_ids: Set[str],
) -> tuple[int, List[str]]:
    """Count preds that reference unknown ``gt_state_id``."""

    tags: List[str] = []
    n = 0
    for r in predicted_rows:
        bad = False
        if str(r.get("from_state_id") or "") not in gt_state_ids:
            bad = True
        if str(r.get("to_state_id") or "") not in gt_state_ids:
            bad = True
        if bad:
            n += 1
            tags.append("invalid_state_reference")
    return n, tags


def invalid_flow_fraction(
    predicted_flows: List[Dict[str, Any]],
    gt_state_ids: Set[str],
) -> float:
    if not predicted_flows:
        return 0.0
    bad = 0
    for pf in predicted_flows:
        states = pf.get("ordered_state_ids") or []
        if not isinstance(states, list):
            bad += 1
            continue
        if any(str(s) not in gt_state_ids for s in states if s):
            bad += 1
    return bad / len(predicted_flows)
