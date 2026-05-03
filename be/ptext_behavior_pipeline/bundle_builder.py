"""Deterministic JSON aggregation for Stage A (no LLM-invented capture ids)."""

from __future__ import annotations

import json
from typing import Any


def minified_captures_bundle(capture_entries: list[dict[str, Any]]) -> str:
    payload = {"captures_bundle": capture_entries}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
