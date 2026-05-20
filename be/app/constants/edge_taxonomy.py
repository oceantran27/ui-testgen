"""Canonical vocabulary for candidate edge resolution (resolver + Agent 4 prompts).

Aligned with Phase 1 outcome_state_type (`A1OutcomeStateType`) plus legacy tokens."""

from __future__ import annotations

from typing import Dict, Final, FrozenSet, Optional, Tuple

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
        {"success", "confirmation_required", "validation_error", "warning", "error", "neutral"}
    ),
    "confirmation": frozenset({"success", "confirmation_required", "neutral", "empty"}),
    "cancellation": frozenset({"neutral", "empty", "confirmation_required"}),
    "selection": frozenset({"neutral", "empty"}),
    "navigation": frozenset({"neutral", "empty"}),
    "editing": frozenset({"success", "neutral", "validation_error"}),
    "deletion": frozenset({"success", "neutral", "empty", "confirmation_required"}),
    "search": frozenset({"neutral", "empty"}),
    "filtering": frozenset({"neutral", "empty"}),
    "creation": frozenset({"neutral", "empty", "success"}),
    "feedback_acknowledgement": frozenset({"neutral"}),
}

# Resolver output vocabulary for CandidateEdge.edge_kind (after classify_edge_kind).
EDGE_KIND_VALUES: Final[FrozenSet[str]] = frozenset(
    {
        "progress",
        "task_progress",
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

# Edge kinds that satisfy “forward motion” for task_core submission intents in diagnostics.
TASK_PROGRESS_FORWARD_EDGE_KINDS: Final[FrozenSet[str]] = frozenset(
    {
        "task_progress",
        "progress",
        "success_terminal",
        "review_required",
        "confirmation_required",
        "validation_error",
        "warning",
        "error",
        "failure",
        "empty_result",
    }
)

# Target screen types (normalized) allowed for submission → neutral task_progress.
TASK_PROGRESS_TARGET_SCREEN_TYPES: Final[FrozenSet[str]] = frozenset(
    {"form", "detail", "checkout", "listing"}
)

# Allowed (source_screen_type, target_screen_type) neutral→neutral task progress probes (resolver sparse).
WIZARD_PROGRESS_SCREEN_PAIRS: Final[FrozenSet[Tuple[str, str]]] = frozenset(
    {
        ("listing", "detail"),
        ("detail", "form"),
        ("detail", "checkout"),
        ("form", "form"),
        ("form", "listing"),
        ("form", "checkout"),
        ("checkout", "form"),
        ("form", "detail"),
        ("checkout", "listing"),
        ("checkout", "detail"),
        ("checkout", "checkout"),
    }
)

NEUTRAL_WIZARD_FORWARD_SOURCE_SCREEN_TYPES: Final[FrozenSet[str]] = frozenset(
    {"listing", "detail", "form", "checkout", "search"}
)

SCENARIO_ROLE_VALUES: Final[FrozenSet[str]] = frozenset(
    {"core", "branch", "optional", "excluded"}
)

# Scenario pipeline: branch roles used for worthiness / causal gates (orthogonal to SCENARIO_ROLE_VALUES).
SCENARIO_WORTHY_BRANCH_ROLES: Final[FrozenSet[str]] = frozenset(
    {
        "validation_branch",
        "error_branch",
        "warning_branch",
        "empty_result_branch",
        "confirmation_branch",
        "recovery_branch",
        "cancellation_branch",
        "success_terminal",
        "core_progress",
    }
)

NON_SCENARIO_WORTHY_BRANCH_ROLES: Final[FrozenSet[str]] = frozenset(
    {
        "support_navigation",
        "post_success_navigation",
        "global_navigation",
        "local_interaction",
        "chrome_interaction",
    }
)

FATAL_EDGE_RISK_FLAGS: Final[FrozenSet[str]] = frozenset(
    {
        "unresolved_selection_option",
        "ambiguous_selection_requires_evidence",
        "many_compatible_targets",
    }
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
        ("checkout", "form"),
        ("checkout", "checkout"),
        ("dashboard", "detail"),
        ("profile", "settings"),
        ("detail", "form"),
        ("form", "form"),
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


def matrix_transition_allowed(
    intent_kind: str,
    action_scope: str,
    source_outcome: str,
    target_outcome: str,
    *,
    value_bound_selection: bool,
    target_presentation_scope: str = "",
) -> Tuple[bool, Optional[str]]:
    """
    Sparse 4D policy (intent_kind, action_scope, source_outcome, target_outcome).

    Returns (allowed, scenario_branch_role_hint). When hint is None, downstream uses edge_kind defaults.
    Unknown tuples fall back to legacy eligibility only (allowed True).
    """
    ik = str(intent_kind or "").strip()
    asc = str(action_scope or "").strip()
    so = str(source_outcome or "neutral").strip()
    to = str(target_outcome or "neutral").strip()
    tgt_ps = str(target_presentation_scope or "").strip().lower()

    # Selection into negative targets requires binding evidence (resolver supplies flag).
    if ik == "selection" and asc == "task_core" and to in NEGATIVE_OUTCOME_TYPES:
        if not value_bound_selection:
            return False, None
        return True, "validation_branch"

    if ik == "navigation" and asc == "global_navigation":
        return True, "global_navigation"

    if ik == "editing" and to == "review_required":
        return True, "recovery_branch"

    if ik in ("cancellation", "deletion") and to == "confirmation_required":
        if tgt_ps not in ("modal", "overlay", "dialog", "drawer", "popover"):
            return False, None
        return True, "cancellation_branch"

    if ik == "confirmation":
        if to in ("empty", "success"):
            if so != "confirmation_required":
                return False, None
            return True, "confirmation_branch"
        if to in ("neutral", "confirmation_required"):
            return True, "confirmation_branch"
        return True, None

    return True, None


def default_scenario_branch_role(edge_kind: str, intent_kind: str) -> str:
    """Fallback scenario_branch_role when matrix returns no hint."""
    ek = str(edge_kind or "")
    ik = str(intent_kind or "")
    if ek == "success_terminal":
        return "success_terminal"
    if ek == "empty_result":
        return "empty_result_branch"
    if ek == "validation_error":
        return "validation_branch"
    if ek in ("warning", "error", "failure"):
        return "error_branch"
    if ek in ("confirmation_required", "review_required"):
        return "confirmation_branch"
    if ik == "cancellation":
        return "cancellation_branch"
    if ek == "task_progress":
        return "core_progress"
    return "core_progress"
