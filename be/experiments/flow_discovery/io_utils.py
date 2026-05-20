"""JSON I/O helpers (no DB dependencies)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json_document(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(document), f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def read_json_document(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object at {path}")
    return data


def load_or_none(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    return read_json_document(path)
