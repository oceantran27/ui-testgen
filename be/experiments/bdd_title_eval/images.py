from __future__ import annotations

import re
from pathlib import Path

# Common image extensions; case-insensitive match
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

_STEM_ID = re.compile(r"^(\d+)$")


def list_images_by_id(images_dir: Path) -> list[tuple[int, Path]]:
    """
    Return sorted (id, path) for files whose stem is a plain integer, e.g. ``1.png``, ``2.jpg``.
    Skips non-matching or duplicate ids (last file wins in a dict; we detect duplicates).
    """
    if not images_dir.is_dir():
        return []
    by_id: dict[int, Path] = {}
    for f in images_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in _IMAGE_EXTS:
            continue
        m = _STEM_ID.match(f.stem)
        if not m:
            continue
        eid = int(m.group(1))
        if eid in by_id:
            raise ValueError(
                f"Duplicate image id {eid}: {by_id[eid]!s} and {f!s}. "
                "Use one file per id."
            )
        by_id[eid] = f
    return sorted(by_id.items(), key=lambda x: x[0])
