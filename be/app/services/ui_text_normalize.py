"""Shared UI text normalization for deterministic grounding / matching."""

from __future__ import annotations

import re
import unicodedata


def normalize_ui_text(s: str) -> str:
    """Deterministic UI text normalization for matching (no fuzzy semantic similarity)."""
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = t.casefold()
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"([\w\d])([\.,!?;])(?=\s|$|\w)", r"\1 \2 ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t
