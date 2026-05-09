#!/usr/bin/env python3
"""
Preview near-duplicate removal (pHash >95% similarity **and** SSIM >= 0.95) for images in a folder.

Run (from repo backend root):
    cd be
    python scripts/dedup_folder_preview.py

Edit INPUT_FOLDER below to your dataset directory (Windows path or pathlib).
Output: console summary + INPUT_FOLDER / dedup_preview.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# --- configure here ---
INPUT_FOLDER: Path | str = r"C:\sqa-workspace\ui-testgen\be\uploads\multi-img-input\593e720a-0908-4e95-98df-f3b9e445f25e"
OUTPUT_JSON_NAME = "dedup_preview.json"
RECURSIVE = False
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
# ----------------------

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services.image_dedup_service import dedupe_image_paths  # noqa: E402


def _collect_image_paths(folder: Path) -> list[str]:
    if RECURSIVE:
        paths_set: set[Path] = set()
        for suf in IMAGE_SUFFIXES:
            for p in folder.rglob(f"*{suf}"):
                if p.is_file():
                    paths_set.add(p.resolve())
        paths = list(paths_set)
    else:
        paths = []
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
                paths.append(p.resolve())
    return sorted(str(p) for p in paths)


def main() -> int:
    folder = Path(INPUT_FOLDER).expanduser().resolve()
    if not folder.is_dir():
        print(f"ERROR: not a directory: {folder}", file=sys.stderr)
        return 1

    paths = _collect_image_paths(folder)
    if not paths:
        print(f"No images found in {folder} (suffixes: {IMAGE_SUFFIXES}, recursive={RECURSIVE})")
        return 0

    t0 = time.perf_counter()
    result = dedupe_image_paths(paths)
    dedup_processing_s = time.perf_counter() - t0

    print(f"Input folder: {folder}")
    print(f"Files scanned: {len(paths)}")
    print(f"Dedup processing time: {dedup_processing_s:.3f}s")
    print(f"Canonical (kept): {len(result.canonical_paths)}")
    print(f"Dropped (near-duplicate): {len(result.dropped_paths)}")
    print()

    print("=== Canonical (kept) ===")
    for pth, iid in zip(result.canonical_paths, result.canonical_image_ids, strict=True):
        print(f"  {Path(pth).name}")
        print(f"    path: {pth}")
        print(f"    image_id: {iid}")
    print()

    if result.dropped_paths:
        print("=== Dropped (merged into canonical image_id) ===")
        for dp in result.dropped_paths:
            cid = result.input_path_to_image_id.get(dp, "?")
            print(f"  {Path(dp).name}")
            print(f"    dropped: {dp}")
            print(f"    image_id (canonical): {cid}")
        print()

    payload = {
        "input_folder": str(folder),
        "file_count": len(paths),
        "recursive": RECURSIVE,
        "dedup_method": "phash_gt_95pct_and_ssim_ge_0.95",
        "dedup_processing_seconds": round(dedup_processing_s, 6),
        "canonical_paths": result.canonical_paths,
        "canonical_image_ids": result.canonical_image_ids,
        "dropped_paths": result.dropped_paths,
        "input_path_to_image_id": result.input_path_to_image_id,
    }
    out_path = folder / OUTPUT_JSON_NAME
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
