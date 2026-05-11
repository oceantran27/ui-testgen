"""
Lightweight Preprocessing Service — Phase Research v1.
Skips complex quality/viewport validation under controlled input assumption.
"""
import time
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import log_event
from app.db.models.image import Image

async def run_lightweight_preprocessing(db: AsyncSession, run_id: str, image_ids: List[str]) -> Dict[str, Any]:
    """
    Minimal preprocessing: ensure images exist and mark as valid.
    """
    start_time = time.time()
    log_event("lightweight_preprocessing_started", run_id=run_id)

    result = await db.execute(
        select(Image).where(Image.id.in_(image_ids), Image.run_id == run_id)
    )
    images = list(result.scalars().all())

    valid_images = []
    warnings = []

    for img in images:
        if not img.normalized_uri:
            img.normalized_uri = img.storage_uri

        # We assume they are already decoded/normalized if uploaded via standard API
        # but we mark them as valid for the pipeline state.
        valid_images.append({
            "image_id": img.id,
            "original_filename": img.original_filename,
            "is_valid": True,
            "quality_status": "skipped",
            "normalized_uri": img.normalized_uri,
            "thumbnail_uri": img.thumbnail_uri,
            "warnings": []
        })

    await db.commit()

    if settings.SKIP_IMAGE_QUALITY_VALIDATION:
        warnings.append("Image quality and viewport validation are skipped under the controlled input assumption.")

    report = {
        "input_count": len(image_ids),
        "valid_count": len(valid_images),
        "skipped_validation": True,
        "warnings": warnings
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("lightweight_preprocessing_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "valid_images": valid_images,
        "report": report,
        "warnings": warnings
    }
