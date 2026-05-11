"""
Exact Duplicate Service — Phase Research v1.
Detects exact pixel/byte duplicates using SHA256 hashes.
"""
import time
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import log_event
from app.db.models.image import Image

async def run_exact_duplicate_detection(db: AsyncSession, run_id: str, image_ids: List[str]) -> Dict[str, Any]:
    """
    Groups images by SHA256 and identifies canonical images.
    """
    start_time = time.time()
    log_event("exact_duplicate_detection_started", run_id=run_id)

    result = await db.execute(
        select(Image).where(Image.id.in_(image_ids), Image.run_id == run_id)
    )
    images = list(result.scalars().all())

    hash_groups: Dict[str, List[str]] = {}
    for img in images:
        h = img.sha256_hash
        if h not in hash_groups:
            hash_groups[h] = []
        hash_groups[h].append(img.id)

    exact_duplicate_groups = []
    exact_canonical_images = []

    for h, ids in hash_groups.items():
        # Earliest upload_order as canonical
        group_images = [img for img in images if img.id in ids]
        group_images.sort(key=lambda x: x.upload_order)
        canonical = group_images[0]
        
        exact_canonical_images.append(canonical.id)
        
        if len(ids) > 1:
            exact_duplicate_groups.append({
                "group_id": f"dup_exact_{h[:12]}",
                "canonical_image_id": canonical.id,
                "duplicate_image_ids": [img_id for img_id in ids if img_id != canonical.id],
                "reason": "same_sha256_hash"
            })

    report = {
        "input_count": len(image_ids),
        "exact_duplicate_group_count": len(exact_duplicate_groups),
        "canonical_image_count": len(exact_canonical_images)
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("exact_duplicate_detection_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "exact_duplicate_groups": exact_duplicate_groups,
        "exact_canonical_images": exact_canonical_images,
        "report": report
    }
