"""Greedy multiset matching of predicted vs ground-truth transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from experiments.flow_discovery.evaluator.text_normalize import normalize_trigger_text
from experiments.flow_discovery.schemas.evaluation_schema import TransitionMatchItem
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthTransition


@dataclass
class TransitionMatchBundle:
    strict_items: List[TransitionMatchItem] = field(default_factory=list)
    relaxed_items: List[TransitionMatchItem] = field(default_factory=list)
    false_negatives_strict: List[TransitionMatchItem] = field(default_factory=list)
    false_negatives_relaxed: List[TransitionMatchItem] = field(default_factory=list)


def _strict_key(t: GroundTruthTransition) -> Tuple[str, str, str, str]:
    return (
        t.from_state_id,
        t.to_state_id,
        normalize_trigger_text(t.trigger_action_text),
        str(t.outcome_type or "").strip().lower(),
    )


def _relaxed_key(t: GroundTruthTransition) -> Tuple[str, str, str]:
    return (
        t.from_state_id,
        t.to_state_id,
        normalize_trigger_text(t.trigger_action_text),
    )


def _pred_row_to_gtlike(row: Dict[str, Any]) -> GroundTruthTransition:
    return GroundTruthTransition(
        gt_transition_id=str(row.get("pred_transition_id") or ""),
        from_state_id=str(row.get("from_state_id") or ""),
        to_state_id=str(row.get("to_state_id") or ""),
        trigger_action_text=str(row.get("trigger_action_text") or ""),
        outcome_type=str(row.get("outcome_type") or ""),
        proposal_source="prediction",
    )


def match_transitions(
    predicted_rows: List[Dict[str, Any]],
    ground_truth: List[GroundTruthTransition],
) -> TransitionMatchBundle:
    """Match predictions to GT in two independent passes: strict then relaxed-only verdict lists."""

    preds = [_pred_row_to_gtlike(r) for r in predicted_rows]
    gts = list(ground_truth)

    # --- strict ---
    gt_pool = list(gts)
    strict_items: List[TransitionMatchItem] = []
    for i, pr in enumerate(predicted_rows):
        pid = str(pr.get("pred_transition_id") or f"pred_t_{i:03d}")
        pseudo = preds[i]
        found_idx: Optional[int] = None
        for gi, g in enumerate(gt_pool):
            if _strict_key(pseudo) == _strict_key(g):
                found_idx = gi
                break
        if found_idx is not None:
            g = gt_pool.pop(found_idx)
            strict_items.append(
                TransitionMatchItem(
                    pred_transition_id=pid,
                    gt_transition_id=g.gt_transition_id,
                    match_status="true_positive",
                    matched_gt_transition_id=g.gt_transition_id,
                    match_mode="strict",
                ),
            )
        else:
            strict_items.append(
                TransitionMatchItem(
                    pred_transition_id=pid,
                    match_status="false_positive",
                    match_mode="strict",
                    error_tags=["extra_transition"],
                ),
            )

    fn_strict = [
        TransitionMatchItem(
            gt_transition_id=g.gt_transition_id,
            match_status="false_negative",
            error_tags=["missing_transition"],
        )
        for g in gt_pool
    ]

    # --- relaxed (independent 1:1 on full sets) ---
    gt_pool_r = list(gts)
    relaxed_items: List[TransitionMatchItem] = []
    for i, pr in enumerate(predicted_rows):
        pid = str(pr.get("pred_transition_id") or f"pred_t_{i:03d}")
        pseudo = preds[i]
        found_idx = None
        for gi, g in enumerate(gt_pool_r):
            if _relaxed_key(pseudo) == _relaxed_key(g):
                found_idx = gi
                break
        if found_idx is not None:
            g = gt_pool_r.pop(found_idx)
            mode = "relaxed"
            tags: List[str] = []
            if _strict_key(pseudo) != _strict_key(g):
                tags.append("wrong_outcome_type")
            relaxed_items.append(
                TransitionMatchItem(
                    pred_transition_id=pid,
                    gt_transition_id=g.gt_transition_id,
                    match_status="true_positive",
                    matched_gt_transition_id=g.gt_transition_id,
                    match_mode=mode,
                    error_tags=tags,
                ),
            )
        else:
            relaxed_items.append(
                TransitionMatchItem(
                    pred_transition_id=pid,
                    match_status="false_positive",
                    match_mode="relaxed",
                    error_tags=["extra_transition"],
                ),
            )

    fn_relaxed = [
        TransitionMatchItem(
            gt_transition_id=g.gt_transition_id,
            match_status="false_negative",
            error_tags=["missing_transition"],
        )
        for g in gt_pool_r
    ]

    return TransitionMatchBundle(
        strict_items=strict_items,
        relaxed_items=relaxed_items,
        false_negatives_strict=fn_strict,
        false_negatives_relaxed=fn_relaxed,
    )
