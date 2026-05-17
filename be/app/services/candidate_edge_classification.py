"""Deterministic edge_kind and scenario_role classification for candidate edges."""

from __future__ import annotations

from typing import Optional

from app.constants.edge_taxonomy import (
    CHECKPOINT_OUTCOME_TYPES,
    EMPTY_OUTCOME_TYPES,
    NAV_LIKE_SCREEN_TYPES,
    NEGATIVE_OUTCOME_TYPES,
)


def classify_edge_kind(
    intent_kind: str,
    source_outcome: str,
    target_outcome: str,
) -> str:
    """Map target outcome (+ coarse intent/source context hooks) to resolver edge_kind."""
    _ = intent_kind, source_outcome  # reserved for intent/source-conditioned rules later
    if target_outcome in NEGATIVE_OUTCOME_TYPES:
        return target_outcome
    if target_outcome in CHECKPOINT_OUTCOME_TYPES:
        return target_outcome
    if target_outcome in EMPTY_OUTCOME_TYPES:
        return "empty_result"
    if target_outcome == "success":
        return "success_terminal"
    return "progress"


def classify_scenario_role(
    intent_kind: str,
    source_outcome: str,
    target_outcome: str,
    target_screen: Optional[str] = None,
) -> str:
    """Assign scenario_role for downstream flow composition."""
    edge_kind = classify_edge_kind(intent_kind, source_outcome, target_outcome)

    if edge_kind == "success_terminal":
        if intent_kind in {"submission", "confirmation", "editing", "deletion"}:
            return "core"
        return "branch"

    if edge_kind in NEGATIVE_OUTCOME_TYPES or edge_kind in CHECKPOINT_OUTCOME_TYPES:
        return "branch"

    if edge_kind == "empty_result":
        return "branch"

    # progress (neutral / loading / unknown targets, etc.)
    if (
        intent_kind != "navigation"
        and source_outcome == "success"
        and target_screen
        and target_screen in NAV_LIKE_SCREEN_TYPES
    ):
        return "optional"

    if intent_kind == "navigation":
        return "branch"

    return "branch"
