"""
Standalone duplicate (Phase 3) harness — folder of UI screenshots → preprocess → dedup report JSON.

Run from the ``be/`` directory::

    cd be
    python experiments/dedup_standalone.py

Requirements:
- ``STORAGE_*`` / MinIO (or S3-compatible) per ``app.core.config`` (normalize uploads like preprocess).
- Edit ``INPUT_IMAGES_DIR`` to your screenshot folder.

Duplicate logic is **copied to mirror** ``app/services/duplicate_service.py`` (see inline
``# ref: duplicate_service.py`` comments) so this experiment does not modify application code.
"""
from __future__ import annotations

import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── User: input folder and output JSON (change freely) ──
INPUT_IMAGES_DIR: Path = Path(r"C:\Users\daidu\Desktop\flow\shopee")
OUTPUT_JSON_PATH: Path = Path(__file__).resolve().parent / "dedup_standalone_output.json"


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


# ref: duplicate_service.py — _uri_to_key
def _uri_to_key(storage_uri: str) -> str:
    parts = storage_uri.replace("s3://", "").split("/", 1)
    return parts[1] if len(parts) > 1 else storage_uri


# ref: duplicate_service.py — _generate_hashes
def _generate_hashes(image_bytes: bytes) -> Tuple[str, str]:
    import imagehash
    from PIL import Image as PILImage

    with PILImage.open(BytesIO(image_bytes)) as pil_img:
        phash = str(imagehash.phash(pil_img))
        dhash = str(imagehash.dhash(pil_img))
    return phash, dhash


def _generate_group_id() -> str:
    return f"dup_{uuid.uuid4().hex[:12]}"


@dataclass
class DedupImage:
    """In-memory stand-in for ORM Image rows during standalone dedup."""

    id: str
    sha256_hash: str
    phash: Optional[str]
    dhash: Optional[str]
    quality_status: str
    upload_order: int
    original_filename: str
    source_path: str
    normalized_uri: Optional[str]

    duplicate_status: str = "not_checked"
    is_canonical: bool = False
    duplicate_type: Optional[str] = None
    duplicate_reason: Optional[str] = None
    duplicate_group_id: Optional[str] = None
    hash_error: Optional[str] = None


# ref: duplicate_service.py — run_duplicate_detection (lines 107–265), without DB/artifact
def run_dedup_mirror(
    images: List[DedupImage],
    run_id: str,
    settings: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """
    Returns (final_groups, report, extras) where extras holds uncertain_pair_count, note on VLM stub.
    """
    import imagehash

    if not images:
        return [], {}, {"uncertain_pairs_skipped": 0, "tier3_vlm_stub": True}

    # ref: lines 107-138 — tiers 1 & 2
    exact_groups: Dict[str, List[str]] = {}
    for img in images:
        h = img.sha256_hash
        if h not in exact_groups:
            exact_groups[h] = []
        exact_groups[h].append(img.id)

    sha256_representatives = {h: ids[0] for h, ids in exact_groups.items()}
    distinct_ids = list(sha256_representatives.values())

    near_visual_pairs: List[Tuple[str, str, int, str]] = []
    uncertain_skipped = 0
    for i in range(len(distinct_ids)):
        for j in range(i + 1, len(distinct_ids)):
            id_a, id_b = distinct_ids[i], distinct_ids[j]
            img_a = next(im for im in images if im.id == id_a)
            img_b = next(im for im in images if im.id == id_b)
            if not img_a.phash or not img_b.phash:
                continue
            dist = imagehash.hex_to_hash(img_a.phash) - imagehash.hex_to_hash(img_b.phash)
            if dist <= settings.PHASH_NEAR_THRESHOLD:
                near_visual_pairs.append((id_a, id_b, dist, "near_visual"))
            elif dist <= settings.PHASH_UNCERTAIN_THRESHOLD:
                uncertain_skipped += 1
                # ref: lines 136-138 — uncertain, VLM would apply if implemented

    # ref: lines 143-171 — union-find
    parent = {im.id: im.id for im in images}

    def find(i: str) -> str:
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i: str, j: str) -> None:
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    for h, ids in exact_groups.items():
        for k in range(1, len(ids)):
            union(ids[0], ids[k])

    for id_a, id_b, _dist, _dtype in near_visual_pairs:
        union(id_a, id_b)

    groups_dict: Dict[str, List[str]] = {}
    for im in images:
        root = find(im.id)
        if root not in groups_dict:
            groups_dict[root] = []
        groups_dict[root].append(im.id)

    # ref: lines 173-245 — canonical + final_groups (no DB rows)
    final_groups: List[Dict[str, Any]] = []
    for _root_id, member_ids in groups_dict.items():
        if len(member_ids) < 2:
            img = next(im for im in images if im.id == member_ids[0])
            img.duplicate_status = "unique"
            img.is_canonical = True
            img.duplicate_type = "none"
            continue

        group_images = [im for im in images if im.id in member_ids]

        def selection_key(im: DedupImage) -> Tuple[int, int]:
            prefer_valid = 1 if im.quality_status == "valid" else 0
            return (prefer_valid, -im.upload_order)

        group_images.sort(key=selection_key, reverse=True)
        canonical = group_images[0]

        unique_hashes = {im.sha256_hash for im in group_images}
        if len(unique_hashes) == 1:
            dtype = "exact_duplicate"
        else:
            dtype = "near_visual_duplicate"

        g_id = _generate_group_id()
        for im in group_images:
            im.duplicate_group_id = g_id
            im.duplicate_type = dtype
            if im.id == canonical.id:
                im.duplicate_status = "canonical"
                im.is_canonical = True
            else:
                im.duplicate_status = "duplicate"
                im.is_canonical = False
                im.duplicate_reason = f"Duplicate of {canonical.id} ({dtype})"

        final_groups.append(
            {
                "id": g_id,
                "canonical_id": canonical.id,
                "members": member_ids,
                "type": dtype,
            }
        )

    canonical_count = sum(1 for im in images if im.is_canonical)
    report = {
        "run_id": run_id,
        "total_valid_images": len(images),
        "unique_images_count": sum(1 for im in images if im.duplicate_status == "unique"),
        "duplicate_images_count": sum(1 for im in images if im.duplicate_status == "duplicate"),
        "duplicate_groups_count": len(final_groups),
        "canonical_images_count": canonical_count,
        "duplicate_groups": final_groups,
        "unique_image_ids": [im.id for im in images if im.duplicate_status == "unique"],
        "canonical_image_ids": [im.id for im in images if im.is_canonical],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    extras = {
        "uncertain_pairs_skipped": uncertain_skipped,
        "near_visual_pairs_count": len(near_visual_pairs),
        "tier3_vlm_stub": True,
        "tier3_vlm_config_enabled": bool(getattr(settings, "USE_VLM_FOR_DUPLICATE_CHECK", False)),
        "tier3_vlm_note": (
            "USE_VLM_FOR_DUPLICATE_CHECK is True but no VLM call is implemented in "
            "duplicate_service.py (stub); this standalone mirrors that."
            if getattr(settings, "USE_VLM_FOR_DUPLICATE_CHECK", False)
            else None
        ),
    }

    return final_groups, report, extras


def main() -> None:
    _ensure_sys_path()

    from app.core.config import settings
    from app.services.preprocessing_service import (
        build_quality_report,
        run_preprocessing_pipeline_on_bytes,
        viewport_bands_from_settings,
    )
    from app.services.storage_service import storage_service

    input_dir = INPUT_IMAGES_DIR.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"INPUT_IMAGES_DIR is not a directory: {input_dir}")

    allowed = {x.lower() for x in settings.ALLOWED_IMAGE_FORMATS}
    files: List[Path] = []
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

    synthetic_run_id = f"exp_dedup_{uuid.uuid4().hex[:10]}"
    bands = viewport_bands_from_settings()

    per_image: List[Dict[str, Any]] = []
    for idx, path in enumerate(files):
        raw = path.read_bytes()
        raw_sha256 = hashlib.sha256(raw).hexdigest()
        image_id = f"exp_{path.stem}_{idx}"
        fmt = _suffix_to_format(path.suffix)
        assert fmt is not None
        row: Dict[str, Any] = run_preprocessing_pipeline_on_bytes(
            raw,
            image_id=image_id,
            original_filename=path.name,
            metadata_format=fmt,
            run_id=synthetic_run_id,
            bands=bands,
        )
        row["source_path"] = str(path)
        row["raw_sha256"] = raw_sha256
        per_image.append(row)

    aggregate = build_quality_report(synthetic_run_id, per_image)

    # Valid images with normalized_uri — ref: duplicate_service.py _load_valid_images
    dedup_rows: List[DedupImage] = []
    for idx, row in enumerate(per_image):
        if not row.get("is_valid") or not row.get("normalized_uri"):
            continue
        phash: Optional[str] = None
        dhash: Optional[str] = None
        hash_error: Optional[str] = None
        try:
            object_key = _uri_to_key(row["normalized_uri"])
            data = storage_service.download_file(object_key)
            phash, dhash = _generate_hashes(data)
        except Exception as e:
            hash_error = str(e)

        dedup_rows.append(
            DedupImage(
                id=row["image_id"],
                sha256_hash=row["raw_sha256"],
                phash=phash,
                dhash=dhash,
                quality_status=row.get("quality_status") or "valid",
                upload_order=idx,
                original_filename=row.get("original_filename") or "",
                source_path=str(row.get("source_path") or ""),
                normalized_uri=row.get("normalized_uri"),
                hash_error=hash_error,
            )
        )

    final_groups, report, extras = run_dedup_mirror(dedup_rows, synthetic_run_id, settings)

    per_image_dedup: List[Dict[str, Any]] = []
    by_id = {im.id: im for im in dedup_rows}
    for row in per_image:
        iid = row["image_id"]
        if iid in by_id:
            im = by_id[iid]
            per_image_dedup.append(
                {
                    "image_id": im.id,
                    "source_path": im.source_path,
                    "duplicate_status": im.duplicate_status,
                    "is_canonical": im.is_canonical,
                    "duplicate_type": im.duplicate_type,
                    "duplicate_group_id": im.duplicate_group_id,
                    "duplicate_reason": im.duplicate_reason,
                    "phash": im.phash,
                    "dhash": im.dhash,
                    "hash_error": im.hash_error,
                }
            )
        else:
            per_image_dedup.append(
                {
                    "image_id": iid,
                    "source_path": row.get("source_path"),
                    "duplicate_status": "excluded_not_valid_for_dedup",
                    "is_canonical": None,
                    "duplicate_type": None,
                    "duplicate_group_id": None,
                    "duplicate_reason": None,
                    "phash": None,
                    "dhash": None,
                    "hash_error": None,
                }
            )

    out = {
        "run_id": synthetic_run_id,
        "input_dir": str(input_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "settings_snapshot": {
            "PHASH_NEAR_THRESHOLD": settings.PHASH_NEAR_THRESHOLD,
            "PHASH_UNCERTAIN_THRESHOLD": settings.PHASH_UNCERTAIN_THRESHOLD,
            "USE_VLM_FOR_DUPLICATE_CHECK": settings.USE_VLM_FOR_DUPLICATE_CHECK,
        },
        "viewport_constraints": {
            "short_edge_min": bands.short_edge_min,
            "short_edge_max": bands.short_edge_max,
            "long_edge_min": bands.long_edge_min,
            "long_edge_max": bands.long_edge_max,
            "aspect_ratio_min": bands.aspect_ratio_min,
            "aspect_ratio_max": bands.aspect_ratio_max,
        },
        "preprocessing": {
            "aggregate": aggregate,
            "per_image": per_image,
        },
        "duplicate_detection": {
            "report": report,
            "extras": extras,
            "per_image": per_image_dedup,
        },
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(
        f"Wrote {OUTPUT_JSON_PATH} ({len(per_image)} images, "
        f"{report.get('duplicate_groups_count', 0)} duplicate groups)"
    )


if __name__ == "__main__":
    main()
