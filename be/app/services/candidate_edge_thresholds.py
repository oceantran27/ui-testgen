"""Edge-class thresholds and confidence mapping for candidate edges (Layer 3)."""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Tuple

from app.constants.edge_taxonomy import CHECKPOINT_OUTCOME_TYPES, NEGATIVE_OUTCOME_TYPES
from app.core.config import settings


def _edge_class_keep_threshold_min() -> Dict[str, int]:
    acc = settings.CANDIDATE_EDGE_ACCEPT_THRESHOLD
    return {
        "neutral_progress": settings.CANDIDATE_EDGE_NEUTRAL_PROGRESS_THRESHOLD,
        "submission_success": acc,
        "submission_negative": settings.CANDIDATE_EDGE_NEGATIVE_THRESHOLD,
        "submission_checkpoint": acc,
        "selection_target": acc,
        "navigation_target": acc,
        "cancellation_target": acc,
        "search_target": acc,
        "deletion_target": acc,
        "feedback_ack_target": settings.CANDIDATE_EDGE_FEEDBACK_ACK_THRESHOLD,
        "editing_generic": acc,
        "confirmation_generic": acc,
        "default": acc,
    }

HEAVY_RISK_FLAGS: FrozenSet[str] = frozenset(
    {
        "unresolved_selection_option",
        "ambiguous_selection_requires_evidence",
    }
)

CONFIDENCE_HIGH_BLOCK_FLAGS: FrozenSet[str] = frozenset(
    {
        "unresolved_selection_option",
        "ambiguous_selection_requires_evidence",
        "many_compatible_targets",
    }
)


def derive_edge_class(
    intent_kind: str,
    source_outcome: str,
    target_outcome: str,
    edge_kind: str,
) -> str:
    if intent_kind == "feedback_acknowledgement":
        return "feedback_ack_target"
    if edge_kind == "progress" and source_outcome == "neutral" and target_outcome == "neutral":
        return "neutral_progress"
    if intent_kind == "submission":
        if edge_kind == "success_terminal":
            return "submission_success"
        if edge_kind in NEGATIVE_OUTCOME_TYPES:
            return "submission_negative"
        if edge_kind in CHECKPOINT_OUTCOME_TYPES:
            return "submission_checkpoint"
        return "default"
    if intent_kind == "selection":
        return "selection_target"
    if intent_kind == "navigation":
        return "navigation_target"
    if intent_kind == "cancellation":
        return "cancellation_target"
    if intent_kind == "search":
        return "search_target"
    if intent_kind == "deletion":
        return "deletion_target"
    if intent_kind == "editing":
        return "editing_generic"
    if intent_kind == "confirmation":
        return "confirmation_generic"
    return "default"


def classify_confidence(score: int, risk_flags: List[str]) -> str:
    """Map numeric score + risk flags to edge confidence."""
    flag_set = set(risk_flags)
    blocks_high = bool(flag_set & CONFIDENCE_HIGH_BLOCK_FLAGS)
    strong = settings.CANDIDATE_EDGE_STRONG_THRESHOLD
    accept = settings.CANDIDATE_EDGE_ACCEPT_THRESHOLD
    weak = settings.CANDIDATE_EDGE_WEAK_THRESHOLD
    if score >= strong and not blocks_high:
        return "high"
    if score >= accept:
        return "medium"
    if score >= weak:
        return "low"
    return "low"


def keep_threshold_for_class(edge_class: str, overrides: Dict[str, int] | None = None) -> int:
    table = _edge_class_keep_threshold_min()
    base = table.get(edge_class, table["default"])
    if not overrides:
        return base
    return int(overrides.get(edge_class, overrides.get("default", base)))


def should_keep_edge(
    score: int,
    edge_class: str,
    risk_flags: List[str],
    *,
    prune_threshold: int,
    weak_threshold: int,
    threshold_overrides: Dict[str, int] | None = None,
    allow_weak_band: bool = True,
) -> Tuple[bool, str]:
    """
    Layer 3 prune + class threshold.

    Weak band [weak_threshold, min_keep): keep only without heavy risk flags.
    Below prune_threshold: drop.
    """
    if score < prune_threshold:
        return False, "below_prune_threshold"

    min_keep = keep_threshold_for_class(edge_class, threshold_overrides)

    if score >= min_keep:
        return True, "accepted"

    heavy = HEAVY_RISK_FLAGS.intersection(risk_flags)
    if allow_weak_band and score >= weak_threshold and not heavy:
        return True, "accepted_weak_band"

    return False, "below_class_threshold"
