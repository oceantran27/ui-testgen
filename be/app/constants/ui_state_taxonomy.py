"""Single source of truth for Phase A (ui_state) enums — joint_screen_understanding_v1.

Referenced by model_providers/schemas (Literal types), persist normalization, and compression."""

from __future__ import annotations

from typing import Final

from app.constants.ui_screen_taxonomy import normalize_screen_type as _normalize_screen_type_layout

# ── Presentation / outcome / domain (prompt §3.1) ────────────────────────────

PRESENTATION_SCOPE_ORDERED: Final[tuple[str, ...]] = (
    "full_screen",
    "modal",
    "drawer",
    "popover",
    "toast",
    "banner",
    "inline",
    "overlay",
    "unknown",
)
PRESENTATION_SCOPE_VALUES: Final[frozenset[str]] = frozenset(PRESENTATION_SCOPE_ORDERED)


OUTCOME_STATE_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "neutral",
    "success",
    "error",
    "validation_error",
    "warning",
    "empty",
    "loading",
    "unknown",
)
OUTCOME_STATE_TYPE_VALUES: Final[frozenset[str]] = frozenset(OUTCOME_STATE_TYPE_ORDERED)

LEGACY_OUTCOME_STATE_MAP: Final[dict[str, str]] = {
    "confirmation_required": "neutral",
    "review_required": "neutral",
    "failure": "error",
}


DOMAIN_ORDERED: Final[tuple[str, ...]] = (
    "authentication",
    "ecommerce",
    "healthcare",
    "banking",
    "education",
    "travel",
    "productivity",
    "admin",
    "unknown",
)
DOMAIN_VALUES: Final[frozenset[str]] = frozenset(DOMAIN_ORDERED)


def normalize_domain(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return "unknown"
    if s in DOMAIN_VALUES:
        return s
    return "unknown"


def normalize_outcome_state_type(raw: str | None) -> str:
    """Map legacy DB/LLM tokens to current prompt-aligned vocabulary."""
    s = (raw or "neutral").strip().lower() or "neutral"
    if s in LEGACY_OUTCOME_STATE_MAP:
        s = LEGACY_OUTCOME_STATE_MAP[s]
    return s if s in OUTCOME_STATE_TYPE_VALUES else "unknown"


def normalize_presentation_scope(raw: str | None) -> str:
    s = (raw or "unknown").strip().lower() or "unknown"
    return s if s in PRESENTATION_SCOPE_VALUES else "unknown"


# ── Element / action vocabulary (prompt §3.2–§3.3) ───────────────────────────

ELEMENT_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "heading",
    "text",
    "image",
    "icon",
    "button",
    "link",
    "input",
    "textarea",
    "select",
    "checkbox",
    "radio",
    "switch",
    "slider",
    "date_picker",
    "file_input",
    "tab",
    "menu_item",
    "breadcrumb",
    "pagination",
    "list",
    "list_item",
    "card",
    "table",
    "table_row",
    "table_cell",
    "divider",
    "badge",
    "tag",
    "avatar",
    "progress",
    "container",
    "other",
)
ELEMENT_TYPE_VALUES: Final[frozenset[str]] = frozenset(ELEMENT_TYPE_ORDERED)


def normalize_element_type(raw: str | None) -> str:
    """Coerce unknown LLM/GT element_type tokens to ``other``."""
    s = (raw or "other").strip().lower() or "other"
    return s if s in ELEMENT_TYPE_VALUES else "other"


ROLE_HINT_ORDERED: Final[tuple[str, ...]] = (
    "primary_action",
    "secondary_action",
    "tertiary_action",
    "required_input",
    "optional_input",
    "navigation",
    "feedback",
    "status",
    "informative",
    "decorative",
    "disabled",
    "other",
    "unknown",
)
ROLE_HINT_VALUES: Final[frozenset[str]] = frozenset(ROLE_HINT_ORDERED)

LEGACY_ROLE_HINT_MAP: Final[dict[str, str]] = {
    "status_indicator": "status",
}


def normalize_role_hint(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s in LEGACY_ROLE_HINT_MAP:
        s = LEGACY_ROLE_HINT_MAP[s]
    return s if s in ROLE_HINT_VALUES else None


ACTION_PRIORITY_ORDERED: Final[tuple[str, ...]] = (
    "primary",
    "secondary",
    "tertiary",
    "destructive",
)
ACTION_PRIORITY_VALUES: Final[frozenset[str]] = frozenset(ACTION_PRIORITY_ORDERED)


def normalize_action_priority(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return s if s in ACTION_PRIORITY_VALUES else None


FEEDBACK_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "success",
    "error",
    "validation_error",
    "warning",
    "info",
    "loading",
    "progress",
    "empty",
    "confirmation",
    "unknown",
)
FEEDBACK_TYPE_VALUES: Final[frozenset[str]] = frozenset(FEEDBACK_TYPE_ORDERED)


def normalize_feedback_type(raw: str | None) -> str:
    s = (raw or "unknown").strip().lower() or "unknown"
    return s if s in FEEDBACK_TYPE_VALUES else "unknown"


GROUP_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "navigation",
    "form",
    "search",
    "filter",
    "toolbar",
    "dialog",
    "card",
    "list",
    "table",
    "tabs",
    "menu",
    "feedback",
    "empty_state",
    "content_section",
    "media",
    "footer",
    "header",
    "other",
    "unknown",
)
GROUP_TYPE_VALUES: Final[frozenset[str]] = frozenset(GROUP_TYPE_ORDERED)

LEGACY_GROUP_TYPE_MAP: Final[dict[str, str]] = {
    "list_item": "list",
}


def normalize_group_type(raw: str | None) -> str:
    s = (raw or "other").strip().lower() or "other"
    if s in LEGACY_GROUP_TYPE_MAP:
        s = LEGACY_GROUP_TYPE_MAP[s]
    return s if s in GROUP_TYPE_VALUES else "other"


GROUP_EVIDENCE_TYPE_ORDERED: Final[tuple[str, ...]] = (
    "proximity",
    "common_region",
    "visual_similarity",
    "alignment",
    "explicit_container",
    "shared_label",
    "functional_relation",
)
GROUP_EVIDENCE_TYPE_VALUES: Final[frozenset[str]] = frozenset(GROUP_EVIDENCE_TYPE_ORDERED)


GROUP_CONFIDENCE_VALUES: Final[frozenset[str]] = frozenset(("high", "medium", "low"))

VISUAL_REGION_ORDERED: Final[tuple[str, ...]] = (
    "top_bar",
    "navigation",
    "sidebar",
    "main",
    "footer",
    "bottom_bar",
    "dialog",
    "drawer",
    "popover",
    "toast",
    "overlay",
    "unknown",
)
VISUAL_REGION_VALUES: Final[frozenset[str]] = frozenset(VISUAL_REGION_ORDERED)

# Legacy UI-state-evidence-v2 / ad-hoc region labels → joint vision A1VisualRegion.
LEGACY_VISUAL_REGION_MAP: Final[dict[str, str]] = {
    "header": "top_bar",
    "main_content": "main",
    "modal": "dialog",
}


def normalize_group_evidence_type(raw: str | None) -> str:
    s = (raw or "explicit_container").strip().lower() or "explicit_container"
    return s if s in GROUP_EVIDENCE_TYPE_VALUES else "explicit_container"


def normalize_visual_region(raw: str | None) -> str:
    """Same symbols as schemas A1VisualRegion."""
    s = (raw or "unknown").strip().lower() or "unknown"
    if s in LEGACY_VISUAL_REGION_MAP:
        s = LEGACY_VISUAL_REGION_MAP[s]
    return s if s in VISUAL_REGION_VALUES else "unknown"


def normalize_screen_type_joint(raw: str | None) -> str:
    """screen_type normalized to canonical layout vocab (wizard_step aliases → form/checkout/listing via ui_screen_taxonomy)."""
    return _normalize_screen_type_layout(raw)
