"""
Standalone preprocessing harness — exercises the full per-image preprocessing pipeline from local disk.

Run from the ``be/`` directory::

    cd be
    python experiments/preprocess_standalone.py

Requirements:
- ``STORAGE_*`` / MinIO (or S3-compatible) must match ``app.core.config`` settings.
  Normalize + thumbnail steps call ``storage_service.upload_file``; if storage is down,
  those steps fail with errors in the per-image output.

Edit ``INPUT_IMAGES_DIR`` below to point at a folder of screenshots (png / jpg / jpeg / webp).
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── User: set your input folder here (raw string path on Windows is fine) ──
INPUT_IMAGES_DIR: Path = Path(r"C:\Users\daidu\Desktop\flow\shopee")

# Where to write the combined report JSON
OUTPUT_JSON_PATH: Path = Path(__file__).resolve().parent / "preprocessing_standalone_output.json"


def _be_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_sys_path() -> None:
    root = str(_be_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _suffix_to_format(suffix: str) -> str | None:
    s = suffix.lower().lstrip(".")
    if s == "jpeg":
        return "jpg"
    if s in ("png", "jpg", "webp"):
        return s
    return None


def main() -> None:
    _ensure_sys_path()

    from app.core.config import settings
    from app.services.preprocessing_service import (
        build_quality_report,
        run_preprocessing_pipeline_on_bytes,
        viewport_bands_from_settings,
    )

    input_dir = INPUT_IMAGES_DIR.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"INPUT_IMAGES_DIR is not a directory: {input_dir}")

    allowed = {x.lower() for x in settings.ALLOWED_IMAGE_FORMATS}
    files: list[Path] = []
    for p in sorted(input_dir.iterdir()):
        if not p.is_file():
            continue
        fmt = _suffix_to_format(p.suffix)
        if fmt and fmt in allowed:
            files.append(p)

    if not files:
        raise SystemExit(
            f"No images with extensions {sorted(allowed)} found under {input_dir}"
        )

    synthetic_run_id = f"exp_{uuid.uuid4().hex[:10]}"
    bands = viewport_bands_from_settings()

    per_image: list[dict] = []
    for idx, path in enumerate(files):
        raw = path.read_bytes()
        image_id = f"exp_{path.stem}_{idx}"
        fmt = _suffix_to_format(path.suffix)
        assert fmt is not None
        row = run_preprocessing_pipeline_on_bytes(
            raw,
            image_id=image_id,
            original_filename=path.name,
            metadata_format=fmt,
            run_id=synthetic_run_id,
            bands=bands,
        )
        row["source_path"] = str(path)
        per_image.append(row)

    aggregate = build_quality_report(synthetic_run_id, per_image)

    out = {
        "run_id": synthetic_run_id,
        "input_dir": str(input_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "viewport_constraints": {
            "short_edge_min": bands.short_edge_min,
            "short_edge_max": bands.short_edge_max,
            "long_edge_min": bands.long_edge_min,
            "long_edge_max": bands.long_edge_max,
            "aspect_ratio_min": bands.aspect_ratio_min,
            "aspect_ratio_max": bands.aspect_ratio_max,
        },
        "aggregate": aggregate,
        "per_image": per_image,
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_JSON_PATH} ({len(per_image)} images)")


if __name__ == "__main__":
    main()
