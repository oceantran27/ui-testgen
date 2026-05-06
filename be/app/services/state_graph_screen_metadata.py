"""Derive per-screen fields for state-graph Gemini input (see state_graph_from_ui_intents prompt)."""

from __future__ import annotations

from typing import Any

from app.schemas.ui_extraction import UIExtractionResult, UIExtractedControl


_HEADING_ROLES = frozenset(
    {"heading", "title", "banner", "heading1", "heading2", "heading3", "region", "header"}
)
_NAV_LINK_ROLES = frozenset({"link", "tab", "menuitem"})
_MIN_PROMINENT_LEN = 12


def _display_text(c: UIExtractedControl) -> str:
    v = (c.value or "").strip()
    if v:
        return v
    return (c.label or "").strip()


def _dedupe_ordered(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in labels:
        t = (x or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def navigational_destinations_from_extraction(extraction: UIExtractionResult) -> list[str]:
    labels: list[str] = []
    for g in extraction.groups:
        if not g.destinations:
            continue
        for d in g.destinations:
            labels.append(d.label)
    by_group = _dedupe_ordered(labels)

    link_texts: list[str] = []
    for c in extraction.controls:
        if (c.role or "").strip().lower() not in _NAV_LINK_ROLES:
            continue
        t = _display_text(c)
        if t:
            link_texts.append(t)

    return _dedupe_ordered(by_group + link_texts)


def primary_heading_from_extraction(extraction: UIExtractionResult) -> str:
    page_summary = (extraction.overview.viewport_description or "").strip()

    for c in extraction.controls:
        role = (c.role or "").strip().lower()
        if role in _HEADING_ROLES:
            t = _display_text(c)
            if t:
                return t

    for c in extraction.controls:
        role = (c.role or "").strip().lower()
        if role != "tab":
            continue
        if c.states.selected is True:
            t = _display_text(c)
            if t:
                return t

    for c in extraction.controls:
        role = (c.role or "").strip().lower()
        if role not in ("button", "link"):
            continue
        t = _display_text(c)
        if len(t) >= _MIN_PROMINENT_LEN:
            return t

    return page_summary


def build_state_graph_screen_dict(
    *,
    image_id: str,
    extraction: UIExtractionResult,
    user_intents: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build one element of `screens` for `run_state_graph_flow_sync` / screens_bundle.json.
    Keys match prompt §2 (no interactive_element_count).
    """
    page_summary = (extraction.overview.viewport_description or "").strip()
    return {
        "image_id": image_id,
        "ui_state_type": "full_page",
        "primary_heading": primary_heading_from_extraction(extraction),
        "page_summary": page_summary,
        "navigational_destinations": navigational_destinations_from_extraction(extraction),
        "user_intents": user_intents,
    }
