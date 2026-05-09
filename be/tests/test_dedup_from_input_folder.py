"""
Integration-style test: run perceptual dedup on all images under a folder.

Set ``DEDUP_INPUT_FOLDER`` to a filesystem path, or ``DEDUP_INPUT_FOLDER_URL`` to a
``file:///`` URL (e.g. ``file:///C:/Screenshots/batch1``). If neither is set or the
path is missing, the test is skipped so CI stays green.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest

from app.services.image_dedup_service import dedupe_image_paths

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _resolve_folder_from_env() -> Path | None:
    raw = (os.environ.get("DEDUP_INPUT_FOLDER_URL") or os.environ.get("DEDUP_INPUT_FOLDER") or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("file:"):
        parsed = urlparse(raw)
        local = url2pathname(parsed.path)
        return Path(local).expanduser().resolve()
    return Path(raw).expanduser().resolve()


def _collect_image_paths(folder: Path) -> list[str]:
    return sorted(
        {
            str(p.resolve())
            for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
        }
    )


@pytest.mark.integration
def test_dedup_preprocessing_from_input_folder() -> None:
    folder = _resolve_folder_from_env()
    if folder is None:
        pytest.skip(
            "Set DEDUP_INPUT_FOLDER (path) or DEDUP_INPUT_FOLDER_URL (file:///...) "
            "to a folder of screenshots to run this test."
        )
    if not folder.is_dir():
        pytest.skip(f"Input folder does not exist or is not a directory: {folder}")

    paths = _collect_image_paths(folder)
    if not paths:
        pytest.skip(f"No images with supported extensions under {folder}")

    result = dedupe_image_paths(paths)

    assert len(result.canonical_paths) >= 1
    assert len(result.canonical_paths) <= len(paths)
    assert len(result.canonical_image_ids) == len(result.canonical_paths)

    for p in paths:
        assert p in result.input_path_to_image_id
        cid = result.input_path_to_image_id[p]
        assert len(cid) == 64  # sha256 hex

    for canon_path, cid in zip(result.canonical_paths, result.canonical_image_ids, strict=True):
        assert result.input_path_to_image_id[canon_path] == cid

    dropped_set = set(result.dropped_paths)
    for p in result.dropped_paths:
        assert p in dropped_set
        assert result.input_path_to_image_id[p] in result.canonical_image_ids
