"""Canonical vocabulary for candidate edge resolution (resolver + Agent 4 prompts).

Aligned with Phase 1 outcome_state_type (`A1OutcomeStateType`) plus legacy tokens."""

from __future__ import annotations

from typing import Dict, Final, FrozenSet

# Union of pipeline outcomes + legacy DB/backfill tokens
OUTCOME_TYPES: Final[FrozenSet[str]] = frozenset(
    {
        "neutral",
        "success",
        "error",
        "validation_error",
        "warning",
        "empty",
        "loading",
        "confirmation_required",
        "review_required",
        "unknown",
        "failure",  # legacy alias still seen in older rows / migrations
    }
)

NEGATIVE_OUTCOME_TYPES: Final[FrozenSet[str]] = frozenset(
    {"validation_error", "warning", "error", "failure"}
)
TERMINAL_OUTCOME_TYPES: Final[FrozenSet[str]] = frozenset({"success"})
CHECKPOINT_OUTCOME_TYPES: Final[FrozenSet[str]] = frozenset(
    {"confirmation_required", "review_required"}
)
EMPTY_OUTCOME_TYPES: Final[FrozenSet[str]] = frozenset({"empty"})

# Intent kind → eligible target outcome_state_type values for resolver pairing.
INTENT_TO_TARGET_OUTCOME_COMPATIBILITY: Final[Dict[str, FrozenSet[str]]] = {
    "submission": frozenset(
        {"success", "confirmation_required", "validation_error", "warning", "error"}
    ),
    "confirmation": frozenset({"success", "confirmation_required", "neutral"}),
    "cancellation": frozenset({"neutral", "empty"}),
    "selection": frozenset({"neutral", "empty"}),
    "navigation": frozenset({"neutral", "empty"}),
    "editing": frozenset({"success", "neutral", "validation_error"}),
    "deletion": frozenset({"success", "neutral", "empty"}),
    "search": frozenset({"neutral", "empty"}),
    "feedback_acknowledgement": frozenset({"neutral"}),
}

# Resolver output vocabulary for CandidateEdge.edge_kind (after classify_edge_kind).
EDGE_KIND_VALUES: Final[FrozenSet[str]] = frozenset(
    {
        "progress",
        "success_terminal",
        "empty_result",
        "validation_error",
        "warning",
        "error",
        "failure",
        "confirmation_required",
        "review_required",
    }
)

SCENARIO_ROLE_VALUES: Final[FrozenSet[str]] = frozenset(
    {"core", "branch", "optional", "excluded"}
)

# Conservative (src_screen_type, dst_screen_type) pairs → eligible for transition bonus.
SCREEN_TRANSITION_BONUS_PAIRS: Final[FrozenSet[tuple[str, str]]] = frozenset(
    {
        ("form", "detail"),
        ("form", "checkout"),
        ("form", "listing"),
        ("listing", "detail"),
        ("search", "listing"),
        ("search", "detail"),
        ("cart", "checkout"),
        ("wizard_step", "wizard_step"),
        ("wizard_step", "detail"),
        ("wizard_step", "success"),
        ("dashboard", "detail"),
        ("profile", "settings"),
    }
)

NAV_LIKE_SCREEN_TYPES: Final[FrozenSet[str]] = frozenset({"landing", "support"})

# Screens treated as generic/global navigation sinks for submission penalties (extends NAV_LIKE).
GENERIC_GLOBAL_NAV_SCREEN_TYPES: Final[FrozenSet[str]] = frozenset(
    {"landing", "support", "dashboard", "profile", "settings"}
)

# Source outcomes that should not emit cross-state edges unless intent is escape/navigation-like.
SOURCE_TERMINAL_OUTCOME_TYPES: Final[FrozenSet[str]] = frozenset(
    {
        "success",
        "confirmation_required",
        "review_required",
        "error",
        "failure",
        "validation_error",
    }
)

INTENTS_ALLOWED_FROM_TERMINAL_SOURCE: Final[FrozenSet[str]] = frozenset(
    {"navigation", "cancellation", "feedback_acknowledgement"}
)

# Explicitly disallowed transitions (src_screen_type, dst_screen_type); optional tightening beyond absence from bonus set.
SCREEN_TRANSITION_DENIED_PAIRS: Final[FrozenSet[tuple[str, str]]] = frozenset()


def transition_pair_allowed(src_screen: str, dst_screen: str) -> bool:
    """True if pair is not denied and either matches bonus matrix or is unknown/neutral."""
    pair = (src_screen, dst_screen)
    if pair in SCREEN_TRANSITION_DENIED_PAIRS:
        return False
    return True


def transition_pair_bonus_eligible(src_screen: str, dst_screen: str) -> bool:
    return (src_screen, dst_screen) in SCREEN_TRANSITION_BONUS_PAIRS


def eligible_targets(intent_kind: str | None) -> FrozenSet[str]:
    """Return allowed target outcome_state_type strings for this intent_kind (empty if unknown)."""
    if not intent_kind:
        return frozenset()
    return INTENT_TO_TARGET_OUTCOME_COMPATIBILITY.get(intent_kind, frozenset())
