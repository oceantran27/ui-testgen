"""Paths and helpers for temp ground truth JSON (module 2)."""

from __future__ import annotations

from pathlib import Path

from experiments.ui_state_extraction.services.raw_output_persistence_service import (
    path_for_manifest,
    write_json_document,
)


def temp_gt_file_path(temp_gt_dir: Path, relative_path: str, stem: str) -> Path:
    rel = Path(relative_path)
    parent = rel.parent if rel.parent != Path(".") else Path()
    return temp_gt_dir / parent / f"{stem}.temp_gt.json"


__all__ = ["path_for_manifest", "temp_gt_file_path", "write_json_document"]
