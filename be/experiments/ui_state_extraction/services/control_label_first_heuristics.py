"""Heuristics for label-first vs value-first mistakes on input-like controls (module 2 flags)."""

from __future__ import annotations

import re
from typing import Any

# Aligned with joint screen understanding taxonomy; broad enough for UI prompts.
_CONTROL_ELEMENT_TYPES: frozenset[str] = frozenset(
    {
        "input",
        "text_field",
        "password_field",
        "search_field",
        "textarea",
        "text_input",
        "email_field",
        "phone_field",
        "number_field",
        "checkbox",
        "radio",
        "switch",
        "combobox",
        "slider",
        "date_picker",
    }
)
_INPUT_ROLE_HINTS: frozenset[str] = frozenset({"required_input", "optional_input"})

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def _primary_non_empty_text(texts: list[str]) -> str | None:
    for t in texts:
        s = str(t).strip()
        if s:
            return s
    return None


def _looks_like_email_value(s: str) -> bool:
    return bool(_EMAIL_RE.match(s.strip()))


def _looks_like_masked_value(s: str) -> bool:
    """Dots/asterisks bullets — typical masked password or redacted value."""
    t = s.strip()
    if len(t) < 3:
        return False
    mask_chars = frozenset(".*•·●")
    if all(c in mask_chars for c in t):
        return True
    hits = sum(1 for c in t if c in mask_chars)
    return hits / len(t) >= 0.75


def is_control_label_first_candidate(*, element_type: str, role_hint: Any) -> bool:
    et = (element_type or "").strip().lower()
    rh = (str(role_hint).strip().lower() if role_hint is not None else "") or ""
    if rh in _INPUT_ROLE_HINTS:
        return True
    return et in _CONTROL_ELEMENT_TYPES or et == "input"


def control_label_first_flags_for_element(
    gt_element_id: str,
    texts: list[str],
    *,
    element_type: str,
    role_hint: Any,
) -> list[str]:
    """Return auto_flag strings (empty if not a control candidate or no suspicious primary text)."""
    if not is_control_label_first_candidate(element_type=element_type, role_hint=role_hint):
        return []
    primary = _primary_non_empty_text(texts)
    if not primary:
        return []

    looks_email = _looks_like_email_value(primary)
    looks_masked = _looks_like_masked_value(primary)

    out: list[str] = []
    if looks_email:
        out.append(f"control_primary_text_looks_like_value:{gt_element_id}")
    if looks_masked:
        out.append(f"control_primary_text_masked_value:{gt_element_id}")
    if looks_email or looks_masked:
        out.append(f"control_label_maybe_missing:{gt_element_id}")

    return out
