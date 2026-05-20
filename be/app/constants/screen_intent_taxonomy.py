"""Single source of truth for Phase 2 screen behaviour intent extraction enums.

Referenced by prompts (rendered in Python), Pydantic LLM schemas, and validators."""

from __future__ import annotations

from typing import Final

# ── Ordered lists (stable bullet order for prompts / docs) ──────────────────

INTENT_KIND_ORDERED: Final[tuple[str, ...]] = (
    "informative",
    "data_entry",
    "selection",
    "search",
    "navigation",
    "submission",
    "confirmation",
    "cancellation",
    "editing",
    "deletion",
    "feedback_acknowledgement",
)
INTENT_KIND_VALUES: Final[frozenset[str]] = frozenset(INTENT_KIND_ORDERED)

STEP_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "enter_input",
    "select_option",
    "toggle_option",
    "invoke_action",
    "navigate",
    "open",
    "close",
    "confirm",
    "cancel",
    "upload",
)
STEP_TYPE_VALUES: Final[frozenset[str]] = frozenset(STEP_TYPE_ORDERED)

VISIBLE_STATUS_ORDERED: Final[tuple[str, ...]] = (
    "selected",
    "unselected",
    "disabled",
    "unknown",
)
VISIBLE_STATUS_VALUES: Final[frozenset[str]] = frozenset(VISIBLE_STATUS_ORDERED)

EVIDENCE_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "element_text",
    "action_text",
    "feedback_text",
    "non_text_label",
    "group_evidence",
    "control_state",
)
EVIDENCE_TYPE_VALUES: Final[frozenset[str]] = frozenset(EVIDENCE_TYPE_ORDERED)

UNRESOLVED_REASON_ORDERED: Final[tuple[str, ...]] = (
    "no_interaction_group",
    "no_grounded_evidence",
    "no_actionable_control",
    "ambiguous_multiple_goals",
    "invalid_source_group_id",
    "invalid_action_reference",
    "invalid_element_reference",
    "invalid_feedback_reference",
    "unsupported_intent_kind",
    "schema_violation",
    "conflicting_action_roles",
    "outcome_prediction_detected",
)
UNRESOLVED_REASON_VALUES: Final[frozenset[str]] = frozenset(UNRESOLVED_REASON_ORDERED)

MODEL_CONFIDENCE_VALUES: Final[frozenset[str]] = frozenset(
    ("high", "medium", "low")
)

OPTION_REF_TYPE_VALUES: Final[frozenset[str]] = frozenset(("element", "action"))

INPUT_FAMILY_ELEMENT_TYPES: Final[frozenset[str]] = frozenset(
    (
        "input",
        "textarea",
        "select",
        "checkbox",
        "radio",
        "switch",
        "slider",
        "date_picker",
    )
)

SEARCH_ACTION_HINTS: Final[frozenset[str]] = frozenset(("search", "type"))

# Phase A available_actions.action_type (prompt_joint_screen_understanding_v1 §3.3)
ACTION_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "type",
    "select",
    "toggle",
    "upload",
    "drag",
    "scroll",
    "open",
    "close",
    "click",
    "unknown",
)
ACTION_TYPE_VALUES: Final[frozenset[str]] = frozenset(ACTION_TYPE_ORDERED)

# Removed from prompt; normalize legacy LLM/GT payloads on ingest.
LEGACY_ACTION_TYPE_MAP: Final[dict[str, str]] = {
    "submit": "click",
    "navigate": "click",
    "confirm": "click",
    "cancel": "click",
}


def normalize_action_type(raw: str | None) -> str:
    s = (raw or "unknown").strip().lower()
    if s in LEGACY_ACTION_TYPE_MAP:
        return LEGACY_ACTION_TYPE_MAP[s]
    return s if s in ACTION_TYPE_VALUES else "unknown"


def taxonomy_bullets(ordered_values: tuple[str, ...]) -> str:
    return "\n".join(f"- `{v}`" for v in ordered_values)
