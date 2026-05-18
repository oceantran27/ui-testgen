"""
Canonical UI screen_type vocabulary shared by vision extraction, prompts, and backend heuristics.

screen_type describes primary task/layout only — not outcome state or presentation chrome
(modal/drawer etc. belong in presentation_scope; success/error/loading/empty belong in outcome_state_type).
"""

from __future__ import annotations

from typing import FrozenSet

# Must stay aligned with prompt_joint_screen_understanding_v1.txt (ui_state contract).
SCREEN_TYPES_CANONICAL: FrozenSet[str] = frozenset(
    {
        "landing",
        "auth",
        "search",
        "listing",
        "detail",
        "form",
        "dashboard",
        "table",
        "cart",
        "checkout",
        "profile",
        "settings",
        "wizard_step",
        "document",
        "media",
        "support",
        "other",
    }
)

# Raw token (already lowercased) -> canonical member of SCREEN_TYPES_CANONICAL.
SCREEN_TYPE_ALIASES: dict[str, str] = {
    "list": "listing",
    "lists": "listing",
    "search_results": "listing",
    "search_result": "listing",
    "results": "listing",
    "catalog": "listing",
    "browse": "listing",
    "wizard": "wizard_step",
    "service_listing_page": "listing",
    "service_catalog": "listing",
    "service_detail_page": "detail",
    "booking_time_selection_page": "wizard_step",
    "appointment_time_selection": "wizard_step",
    "booking_customer_information_page": "form",
    "booking_customer_information_error_page": "form",
    "booking_review_page": "wizard_step",
    "booking_confirmed_page": "wizard_step",
    "booking_slot_unavailable_page": "wizard_step",
    "my_appointments_page": "listing",
    "appointment_cancelled_page": "listing",
    "booking_flow_page": "wizard_step",
}

# Legacy / forbidden-as-layout tokens from older prompts or models -> coerce to canonical layout or other.
SCREEN_TYPE_LEGACY_COERCE: dict[str, str] = {
    # Former screen_types that are really outcome or chrome — drop to other
    "error": "other",
    "success": "other",
    "modal": "other",
    "notification": "other",
    "empty_state": "other",
    "loading": "other",
}

# Screens where structural empty-state text heuristics apply (formerly list/search_results/search).
EMPTY_STATE_HEURISTIC_SCREEN_TYPES: FrozenSet[str] = frozenset(
    {"dashboard", "listing", "search"}
)


def normalize_screen_type(raw: str | None) -> str:
    """Return a canonical screen_type token; unknown inputs become ``other``."""
    if raw is None:
        return "other"
    token = raw.strip().lower()
    if not token:
        return "other"
    if token in SCREEN_TYPE_LEGACY_COERCE:
        return SCREEN_TYPE_LEGACY_COERCE[token]
    if token in SCREEN_TYPE_ALIASES:
        return SCREEN_TYPE_ALIASES[token]
    if token in SCREEN_TYPES_CANONICAL:
        return token
    return "other"


def screen_type_supports_empty_state_heuristic(screen_type: str | None) -> bool:
    return normalize_screen_type(screen_type) in EMPTY_STATE_HEURISTIC_SCREEN_TYPES
