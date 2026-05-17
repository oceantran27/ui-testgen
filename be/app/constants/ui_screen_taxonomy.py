"""
Canonical UI screen_type vocabulary shared by vision extraction, prompts, and backend heuristics.

screen_type describes primary task/layout only — not outcome state or presentation chrome
(modal/drawer etc. belong in presentation_scope; success/error/loading/empty belong in outcome_state_type).
"""

from __future__ import annotations

from typing import FrozenSet

# Must stay aligned with prompt_ui_state_evidence_extraction_v2.txt
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
