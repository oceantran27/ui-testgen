"""Load per-image UI element lists for coverage evaluation."""

from __future__ import annotations

import json
from pathlib import Path


def load_coverage_ground_truth(path: Path) -> dict[int, list[str]]:
    """
    JSON array of objects with ``id`` (int) and ``elements`` (list of canonical UI strings).

    Convention (document for annotators):
    - Use the same scope for every image: either **primary-layer only** (aligns with
      ``filter_scoped_ui_extraction`` + isolated stage 2) or **full viewport**; state
      which you used in your write-up.
    - Each string in ``elements`` should match visible text / placeholder the way a
      user would read it (button label, link text, input placeholder, tab title, etc.).

    Extra keys per object (e.g. ``notes``) are ignored.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("coverage_ground_truth must be a JSON array")
    by_id: dict[int, list[str]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        if eid is None:
            continue
        try:
            key_id = int(eid)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid id in coverage ground truth: {eid!r}") from exc
        elements_raw = entry.get("elements")
        if elements_raw is None:
            by_id[key_id] = []
            continue
        if not isinstance(elements_raw, list):
            raise ValueError(f"id={key_id}: elements must be a JSON array of strings")
        cleaned: list[str] = []
        for x in elements_raw:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if s:
                cleaned.append(s)
        by_id[key_id] = cleaned
    return by_id
