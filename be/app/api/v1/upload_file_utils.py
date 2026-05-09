"""Lightweight upload helpers (no B2/Supabase side effects)."""

from __future__ import annotations

import os
import re


def safe_file_extension(file_name: str, fallback: str = "bin") -> str:
    sanitized_name = (file_name or "").split("?", 1)[0].split("#", 1)[0]
    _, ext = os.path.splitext(sanitized_name)
    normalized = ext.lstrip(".").strip().lower()
    if not normalized:
        return fallback
    return re.sub(r"[^a-z0-9]", "", normalized) or fallback
