"""Write raw JSON experiment outputs under raw_outputs/ mirroring relative paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from experiments.ui_state_extraction.config import PACKAGE_ROOT


def raw_output_file_path(raw_output_dir: Path, relative_path: str, stem: str) -> Path:
    rel = Path(relative_path)
    parent = rel.parent if rel.parent != Path(".") else Path()
    return raw_output_dir / parent / f"{stem}.raw.json"


def path_for_manifest(path: Path) -> str:
    """Path relative to experiments/ui_state_extraction (portable)."""
    try:
        return path.relative_to(PACKAGE_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def write_json_document(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(document), f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)
