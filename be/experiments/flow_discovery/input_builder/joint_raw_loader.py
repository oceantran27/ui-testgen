"""Load joint prompt raw JSON files from a directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.flow_discovery.schemas.input_builder_schema import JointRawFileRecord

_SKIP_NAMES = frozenset(
    {
        "summary.json",
        "evaluation.json",
        "compressed_catalog_package.json",
        "build_report.json",
        "build_report.experiment.json",
    },
)


def _should_skip_file(name: str) -> bool:
    ln = name.lower()
    if ln in _SKIP_NAMES:
        return True
    if "_package" in ln and ln.endswith(".json"):
        return True
    return False


def _resolve_source_image_id(
    raw_name: str,
    payload: dict[str, Any],
    image_map: dict[str, Any] | None,
) -> tuple[str, str | None]:
    original: str | None = None
    if image_map:
        entry = image_map.get(raw_name)
        if isinstance(entry, dict):
            sid = str(entry.get("source_image_id") or "").strip()
            original = str(entry.get("original_filename") or "").strip() or None
            if sid:
                return sid, original
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        mid = str(meta.get("image_id") or "").strip()
        if mid:
            return mid, original
    top = str(payload.get("image_id") or "").strip()
    if top:
        return top, original
    stem = raw_name
    if stem.lower().endswith(".raw.json"):
        stem = stem[: -len(".raw.json")]
    elif stem.lower().endswith(".json"):
        stem = stem[: -len(".json")]
    return stem, original


def iter_joint_input_json_paths(raw_joint_dir: Path | str) -> list[Path]:
    root = Path(raw_joint_dir).resolve()
    out: list[Path] = []
    for p in sorted(root.iterdir()):
        if not p.is_file() or p.suffix.lower() != ".json":
            continue
        if _should_skip_file(p.name):
            continue
        out.append(p)
    return out


class JointRawLoader:
    def load_dir(
        self,
        raw_joint_dir: str,
        image_map_path: str | None = None,
        *,
        strict: bool = False,
    ) -> tuple[list[JointRawFileRecord], list[str]]:
        """Return records and global loader warnings (parse failures when not strict)."""
        root = Path(raw_joint_dir).resolve()
        image_map: dict[str, Any] | None = None
        warnings: list[str] = []
        if image_map_path:
            p = Path(image_map_path).resolve()
            with open(p, encoding="utf-8") as f:
                image_map = json.load(f)
            if not isinstance(image_map, dict):
                msg = f"IMAGE_MAP_NOT_OBJECT:{p.as_posix()}"
                if strict:
                    raise ValueError(msg)
                warnings.append(msg)
                image_map = None

        json_files = iter_joint_input_json_paths(root)
        records: list[JointRawFileRecord] = []
        for path in json_files:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                msg = f"RAW_JSON_PARSE_FAILED:{path.name}:{exc}"
                if strict:
                    raise
                warnings.append(msg)
                continue
            if not isinstance(data, dict):
                msg = f"RAW_JSON_NOT_OBJECT:{path.name}"
                if strict:
                    raise ValueError(msg)
                warnings.append(msg)
                continue
            sid, original = _resolve_source_image_id(path.name, data, image_map)
            if not sid:
                msg = f"MISSING_SOURCE_IMAGE_ID:{path.name}"
                if strict:
                    raise ValueError(msg)
                warnings.append(msg)
                continue
            records.append(
                JointRawFileRecord(
                    raw_file_path=path.as_posix(),
                    raw_file_name=path.name,
                    source_image_id=sid,
                    original_filename=original,
                    raw_payload=data,
                ),
            )
        return records, warnings


__all__ = ["JointRawLoader", "iter_joint_input_json_paths"]
