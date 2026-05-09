"""
Duplicate Detection Service — Logic for detecting exact and near-visual duplicates.

Tier 1: Exact Match (SHA256)
Tier 2: Near-Visual Match (pHash/dHash Hamming distance)
Tier 3: Semantic Verification (VLM hook, disabled by default)
"""
import json
import uuid
import time
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

import imagehash
from PIL import Image as PILImage

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger, log_event
from app.db.models.run import Run
from app.db.models.image import Image
from app.db.models.artifact import Artifact
from app.db.models.duplicate_group import DuplicateGroup
from app.db.models.duplicate_group_member import DuplicateGroupMember
from app.services.storage_service import storage_service


def _generate_group_id() -> str:
    return f"dup_{uuid.uuid4().hex[:12]}"

def _generate_member_id() -> str:
    return f"dgm_{uuid.uuid4().hex[:12]}"

def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"

def _uri_to_key(storage_uri: str) -> str:
    parts = storage_uri.replace("s3://", "").split("/", 1)
    return parts[1] if len(parts) > 1 else storage_uri


# ──────────────────────────────────────────────
# Module 3.1 — Valid Image Loader
# ──────────────────────────────────────────────

async def _load_valid_images(db: AsyncSession, run_id: str) -> List[Image]:
    """Load only valid images with normalized URIs for the run."""
    result = await db.execute(
        select(Image)
        .where(Image.run_id == run_id)
        .where(Image.is_valid == True)
        .where(Image.normalized_uri != None)
        .order_by(Image.upload_order.asc())
    )
    return list(result.scalars().all())


# ──────────────────────────────────────────────
# Module 3.3 — Perceptual Hash Generation
# ──────────────────────────────────────────────

def _generate_hashes(image_bytes: bytes) -> Tuple[str, str]:
    """Generate pHash and dHash for a normalized image."""
    with PILImage.open(BytesIO(image_bytes)) as pil_img:
        phash = str(imagehash.phash(pil_img))
        dhash = str(imagehash.dhash(pil_img))
    return phash, dhash


# ──────────────────────────────────────────────
# Module 3.2, 3.4, 3.5, 3.6 — Detection & Grouping
# ──────────────────────────────────────────────

async def run_duplicate_detection(db: AsyncSession, run_id: str) -> Dict[str, Any]:
    """
    Execute the full duplicate detection pipeline.
    """
    start_time = time.time()
    log_event("duplicate_detection_started", run_id=run_id, node_name="duplicate_detection")

    # 1. Load valid images
    images = await _load_valid_images(db, run_id)
    if not images:
        log_event("duplicate_detection_skipped", run_id=run_id, reason="NO_VALID_IMAGES")
        return {"canonical_images": [], "duplicate_groups": [], "report": {}}

    # 2. Generate perceptual hashes (Module 3.3)
    # We need normalized images for this
    image_data_cache: Dict[str, bytes] = {}
    for img in images:
        if not img.phash or not img.dhash:
            try:
                object_key = _uri_to_key(img.normalized_uri)
                data = storage_service.download_file(object_key)
                image_data_cache[img.id] = data
                phash, dhash = _generate_hashes(data)
                img.phash = phash
                img.dhash = dhash
            except Exception as e:
                logger.error(f"Hash generation failed for {img.id}: {e}")
    
    await db.commit() # Save hashes

    # 3. Detection Tiers
    # Tier 1: Exact SHA256
    exact_groups: Dict[str, List[str]] = {}
    for img in images:
        h = img.sha256_hash
        if h not in exact_groups:
            exact_groups[h] = []
        exact_groups[h].append(img.id)
    
    # Tier 2: Near-Visual (Hamming distance)
    # We use a union-find or similar to group them.
    # For MVP, let's keep it simple: exact sha256 first, then look for near-visuals
    # among the distinct sha256 groups.
    
    # representative_map: which image represents which sha256 group
    sha256_representatives = {h: ids[0] for h, ids in exact_groups.items()}
    distinct_ids = list(sha256_representatives.values())
    
    # Pairwise near-visual comparison
    near_visual_pairs: List[Tuple[str, str, int, str]] = []
    for i in range(len(distinct_ids)):
        for j in range(i + 1, len(distinct_ids)):
            id_a, id_b = distinct_ids[i], distinct_ids[j]
            img_a = next(img for img in images if img.id == id_a)
            img_b = next(img for img in images if img.id == id_b)
            
            dist = imagehash.hex_to_hash(img_a.phash) - imagehash.hex_to_hash(img_b.phash)
            if dist <= settings.PHASH_NEAR_THRESHOLD:
                near_visual_pairs.append((id_a, id_b, dist, "near_visual"))
            elif dist <= settings.PHASH_UNCERTAIN_THRESHOLD:
                # Uncertain - would need VLM if enabled
                pass

    # Tier 3: Semantic (Placeholder/Stub)
    # If settings.USE_VLM_FOR_DUPLICATE_CHECK is True, we'd call VLM here for uncertain pairs.

    # 4. Grouping (Module 3.6)
    # Union-Find to build groups
    parent = {img.id: img.id for img in images}
    def find(i):
        if parent[i] == i: return i
        parent[i] = find(parent[i])
        return parent[i]
    
    def union(i, j):
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # Group exact SHA256 duplicates
    for h, ids in exact_groups.items():
        for k in range(1, len(ids)):
            union(ids[0], ids[k])
    
    # Group near-visual duplicates
    for id_a, id_b, dist, dtype in near_visual_pairs:
        union(id_a, id_b)
    
    # Assemble groups
    groups_dict: Dict[str, List[str]] = {}
    for img in images:
        root = find(img.id)
        if root not in groups_dict:
            groups_dict[root] = []
        groups_dict[root].append(img.id)
    
    # 5. Canonical Selection (Module 3.7)
    final_groups = []
    for root_id, member_ids in groups_dict.items():
        if len(member_ids) < 2:
            # Not a group, just a unique image
            img = next(img for img in images if img.id == member_ids[0])
            img.duplicate_status = "unique"
            img.is_canonical = True
            img.duplicate_type = "none"
            continue
        
        # Select canonical
        group_images = [img for img in images if img.id in member_ids]
        # Sort criteria: 
        # 1. quality_status == 'valid' (no warnings)
        # 2. blur_score desc (higher is sharper)
        # 3. upload_order asc
        def selection_key(img):
            # quality_status starts with 'invalid' or 'warning' or is 'valid'
            is_valid = 1 if img.quality_status == 'valid' else 0
            blur_score = img.preprocessing_json.get('quality_check', {}).get('blur_score', 0) if img.preprocessing_json else 0
            return (is_valid, blur_score, -img.upload_order)
        
        group_images.sort(key=selection_key, reverse=True)
        canonical = group_images[0]
        
        # Determine group duplicate type
        # If all members have same sha256 -> exact_duplicate
        unique_hashes = {img.sha256_hash for img in group_images}
        if len(unique_hashes) == 1:
            dtype = "exact_duplicate"
        else:
            dtype = "near_visual_duplicate"
        
        g_id = _generate_group_id()
        db_group = DuplicateGroup(
            id=g_id,
            run_id=run_id,
            canonical_image_id=canonical.id,
            duplicate_type=dtype,
            confidence=1.0 if dtype == "exact_duplicate" else 0.9
        )
        db.add(db_group)
        
        for img in group_images:
            img.duplicate_group_id = g_id
            img.duplicate_type = dtype
            if img.id == canonical.id:
                img.duplicate_status = "canonical"
                img.is_canonical = True
            else:
                img.duplicate_status = "duplicate"
                img.is_canonical = False
                img.duplicate_reason = f"Duplicate of {canonical.id} ({dtype})"
            
            # Add member record
            dist = 0
            if img.id != canonical.id and img.phash and canonical.phash:
                dist = imagehash.hex_to_hash(img.phash) - imagehash.hex_to_hash(canonical.phash)

            member = DuplicateGroupMember(
                id=_generate_member_id(),
                duplicate_group_id=g_id,
                image_id=img.id,
                run_id=run_id,
                role="canonical" if img.id == canonical.id else "member",
                duplicate_type=dtype,
                hash_distance=dist,
                reason="Canonical" if img.id == canonical.id else f"Matched with canonical (dist={dist})"
            )
            db.add(member)
        
        final_groups.append({
            "id": g_id,
            "canonical_id": canonical.id,
            "members": member_ids,
            "type": dtype
        })

    # 6. Update Run (Module 8.5)
    run_result = await db.execute(select(Run).where(Run.id == run_id))
    run = run_result.scalar_one()
    run.duplicate_groups_count = len(final_groups)
    run.canonical_images = sum(1 for img in images if img.is_canonical)
    
    # 7. Report (Module 3.9)
    report = {
        "run_id": run_id,
        "total_valid_images": len(images),
        "unique_images_count": sum(1 for img in images if img.duplicate_status == "unique"),
        "duplicate_images_count": sum(1 for img in images if img.duplicate_status == "duplicate"),
        "duplicate_groups_count": len(final_groups),
        "canonical_images_count": run.canonical_images,
        "duplicate_groups": final_groups,
        "unique_image_ids": [img.id for img in images if img.duplicate_status == "unique"],
        "canonical_image_ids": [img.id for img in images if img.is_canonical],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    report_bytes = json.dumps(report, indent=2).encode("utf-8")
    report_key = f"artifacts/{run_id}/duplicate_detection/duplicate_detection_report.json"
    report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

    artifact = Artifact(
        id=_generate_artifact_id(),
        run_id=run_id,
        artifact_type="duplicate_detection_report",
        node_name="duplicate_detection",
        storage_uri=report_uri,
        metadata_json={"canonical_images": run.canonical_images, "duplicate_groups": len(final_groups)},
    )
    db.add(artifact)
    
    await db.commit()
    
    duration_ms = int((time.time() - start_time) * 1000)
    log_event("duplicate_detection_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "canonical_images": [img.id for img in images if img.is_canonical],
        "duplicate_groups": final_groups,
        "report": report
    }
