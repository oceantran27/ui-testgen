from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _flatten_strings(value: Any) -> list[str]:
    """Recursively collect every string from nested lists (ground_truth.json may nest arrays)."""
    out: list[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, list):
            for y in x:
                walk(y)

    walk(value)
    return out


def load_ground_truth(path: Path) -> dict[int, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("ground_truth.json must be a JSON array")
    by_id: dict[int, list[str]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        if eid is None:
            continue
        try:
            key_id = int(eid)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid id in ground truth: {eid!r}") from exc
        raw = entry.get("ground_truth")
        if raw is None:
            by_id[key_id] = []
        else:
            by_id[key_id] = _flatten_strings(raw)
    return by_id
