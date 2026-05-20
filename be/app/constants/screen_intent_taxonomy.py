"""Single source of truth for Phase 2 screen behaviour intent extraction enums.

Referenced by prompts (rendered in Python), Pydantic LLM schemas, and validators."""

from __future__ import annotations

from typing import Final

# ── Ordered lists (stable bullet order for prompts / docs) ──────────────────

# prompt_joint_screen_understanding_v1 §4.1 (+ stable ordering for docs)
INTENT_KIND_ORDERED: Final[tuple[str, ...]] = (
    "submission",
    "confirmation",
    "cancellation",
    "navigation",
    "selection",
    "search",
    "filtering",
    "editing",
    "creation",
    "deletion",
    "data_entry",
    "feedback_acknowledgement",
    "informational",
    "other",
    "unknown",
)
INTENT_KIND_VALUES: Final[frozenset[str]] = frozenset(INTENT_KIND_ORDERED)

# Legacy LLM / GT used `informative` for prompt §4.1; Phase A role_hint still uses `informative`.
LEGACY_INTENT_KIND_MAP: Final[dict[str, str]] = {
    "informative": "informational",
}


# §4.4 — local_action_sequence_templates.steps[].step_type
STEP_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "enter_input",
    "select_option",
    "toggle_option",
    "upload_file",
    "drag_item",
    "scroll_view",
    "open_container",
    "close_container",
    "invoke_action",
    "navigate",
    "confirm",
    "cancel",
    "acknowledge_feedback",
)
STEP_TYPE_VALUES: Final[frozenset[str]] = frozenset(STEP_TYPE_ORDERED)

LEGACY_STEP_TYPE_MAP: Final[dict[str, str]] = {
    "open": "open_container",
    "close": "close_container",
    "upload": "upload_file",
}


def normalize_step_type(raw: str | None) -> str:
    s = (raw or "invoke_action").strip().lower()
    if s in LEGACY_STEP_TYPE_MAP:
        s = LEGACY_STEP_TYPE_MAP[s]
    return s if s in STEP_TYPE_VALUES else "invoke_action"


VISIBLE_STATUS_ORDERED: Final[tuple[str, ...]] = (
    "selected",
    "unselected",
    "disabled",
    "unknown",
)
VISIBLE_STATUS_VALUES: Final[frozenset[str]] = frozenset(VISIBLE_STATUS_ORDERED)

# §4.5 evidence_refs[].evidence_type
EVIDENCE_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "element_text",
    "action_text",
    "feedback_text",
    "control_label",
    "control_value",
    "control_state",
    "group_evidence",
    "visual_structure",
    "non_text_icon",
)
EVIDENCE_TYPE_VALUES: Final[frozenset[str]] = frozenset(EVIDENCE_TYPE_ORDERED)

# Evidence refs that anchor to a Phase A element id (joint validation + hydration).
ELEMENT_SCOPED_EVIDENCE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "element_text",
        "control_label",
        "control_value",
        "control_state",
        "visual_structure",
        "non_text_icon",
        # legacy token; map to control_label at parse
        "non_text_label",
    }
)

LEGACY_EVIDENCE_TYPE_MAP: Final[dict[str, str]] = {
    "non_text_label": "control_label",
}


def normalize_evidence_type(raw: str | None) -> str:
    s = (raw or "element_text").strip().lower()
    if s in LEGACY_EVIDENCE_TYPE_MAP:
        s = LEGACY_EVIDENCE_TYPE_MAP[s]
    return s if s in EVIDENCE_TYPE_VALUES else "element_text"


# §4.6 LLM unresolved reason_code + backend-only codes validators may emit
UNRESOLVED_REASON_ORDERED: Final[tuple[str, ...]] = (
    # Prompt §4.6
    "no_actionable_control",
    "passive_content_only",
    "ambiguous_primary_goal",
    "ambiguous_action_role",
    "ambiguous_intent_kind",
    "ambiguous_screen_type",
    "missing_visible_label",
    "unresolved_non_text_icon",
    "duplicate_control_label",
    "invalid_reference",
    "unsupported_pattern",
    "low_confidence",
    "schema_violation",
    "out_of_scope_inference",
    # Backend / validation (persisted on rejected intents)
    "no_interaction_group",
    "no_grounded_evidence",
    "ambiguous_multiple_goals",
    "invalid_source_group_id",
    "invalid_action_reference",
    "invalid_element_reference",
    "invalid_feedback_reference",
    "unsupported_intent_kind",
    "conflicting_action_roles",
    "outcome_prediction_detected",
)
UNRESOLVED_REASON_VALUES: Final[frozenset[str]] = frozenset(UNRESOLVED_REASON_ORDERED)


def normalize_unresolved_reason_code(raw: str | None) -> str:
    s = (raw or "schema_violation").strip().lower()
    return s if s in UNRESOLVED_REASON_VALUES else "schema_violation"


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
        "file_input",
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
