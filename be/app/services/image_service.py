"""
Image Service — business logic for multi-image upload & query.

Handles: validate files, stream-hash, save to MinIO, persist metadata.
"""
import hashlib
import uuid
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple

from fastapi import UploadFile
from PIL import Image as PILImage
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger, log_event
from app.core.errors import (
    RunNotFoundException,
    RunNotUploadableException,
    MaxImageCountExceededException,
)
from app.db.models.run import Run
from app.db.models.image import Image
from app.schemas.image import ImageUploadItem
from app.services.storage_service import storage_service


# Statuses that allow uploads
UPLOADABLE_STATUSES = {"created", "uploading"}

# Map PIL format names to lowercase extensions
_FORMAT_MAP = {
    "PNG": "png",
    "JPEG": "jpg",
    "WEBP": "webp",
}

ALLOWED_EXTENSIONS = set(settings.ALLOWED_IMAGE_FORMATS)


def _generate_image_id() -> str:
    return f"img_{uuid.uuid4().hex[:12]}"


def _compute_sha256_chunked(data: bytes, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash in chunks to keep memory pressure low."""
    h = hashlib.sha256()
    mv = memoryview(data)
    for i in range(0, len(mv), chunk_size):
        h.update(mv[i : i + chunk_size])
    return h.hexdigest()


async def upload_images(
    db: AsyncSession,
    run_id: str,
    files: List[UploadFile],
) -> dict:
    """
    Process a batch upload for a given run.

    Returns a dict ready for UploadImagesResponse.
    Implements *partial success*: valid files are saved even if some fail.
    """

    # ── 1. Validate run ──────────────────────
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise RunNotFoundException(run_id)

    if run.status not in UPLOADABLE_STATUSES:
        raise RunNotUploadableException(run_id, run.status)

    # ── 2. Check total image count limit ─────
    current_count = run.total_images
    max_allowed = settings.MAX_IMAGES_PER_RUN
    if current_count >= max_allowed:
        raise MaxImageCountExceededException(run_id, current_count, max_allowed)

    remaining_slots = max_allowed - current_count
    image_items: List[ImageUploadItem] = []
    uploaded_count = 0
    failed_count = 0
    warnings: List[str] = []

    # Current upload order base
    upload_order_base = current_count

    for idx, file in enumerate(files):
        filename = file.filename or f"unknown_{idx}"

        # ── Guard: slot limit ────────────────
        if uploaded_count >= remaining_slots:
            warnings.append(
                f"Skipped '{filename}': maximum image count ({max_allowed}) reached."
            )
            image_items.append(
                ImageUploadItem(
                    original_filename=filename,
                    upload_status="failed",
                    error_message=f"MAX_IMAGE_COUNT_EXCEEDED (limit {max_allowed})",
                )
            )
            failed_count += 1
            continue

        # ── Read file bytes ──────────────────
        try:
            file_bytes = await file.read()
        except Exception as e:
            logger.error(f"Failed to read file '{filename}': {e}")
            image_items.append(
                ImageUploadItem(
                    original_filename=filename,
                    upload_status="failed",
                    error_message="CORRUPTED_IMAGE_FILE",
                )
            )
            failed_count += 1
            continue

        # ── Guard: empty file ────────────────
        if not file_bytes:
            image_items.append(
                ImageUploadItem(
                    original_filename=filename,
                    upload_status="failed",
                    error_message="EMPTY_FILE",
                )
            )
            failed_count += 1
            continue

        # ── Guard: file too large ────────────
        size_bytes = len(file_bytes)
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if size_bytes > max_bytes:
            image_items.append(
                ImageUploadItem(
                    original_filename=filename,
                    file_size=size_bytes,
                    upload_status="failed",
                    error_message=f"FILE_TOO_LARGE ({size_bytes / (1024*1024):.1f} MB > {settings.MAX_UPLOAD_SIZE_MB} MB)",
                )
            )
            failed_count += 1
            continue

        # ── Decode image (format + dimensions) ──
        try:
            pil_img = PILImage.open(BytesIO(file_bytes))
            pil_img.verify()  # lightweight check
            # Re-open after verify (verify consumes the stream)
            pil_img = PILImage.open(BytesIO(file_bytes))
            width, height = pil_img.size
            pil_format = pil_img.format  # e.g. "PNG", "JPEG"
        except Exception:
            image_items.append(
                ImageUploadItem(
                    original_filename=filename,
                    file_size=size_bytes,
                    upload_status="failed",
                    error_message="CORRUPTED_IMAGE_FILE",
                )
            )
            failed_count += 1
            continue

        # ── Guard: supported format ──────────
        ext = _FORMAT_MAP.get(pil_format, (pil_format or "").lower())
        if ext not in ALLOWED_EXTENSIONS:
            image_items.append(
                ImageUploadItem(
                    original_filename=filename,
                    format=ext,
                    file_size=size_bytes,
                    upload_status="failed",
                    error_message=f"UNSUPPORTED_IMAGE_FORMAT ({ext})",
                )
            )
            failed_count += 1
            continue

        # ── Compute hash (chunked) ───────────
        sha256_hash = _compute_sha256_chunked(file_bytes)

        # ── Upload to storage ────────────────
        image_id = _generate_image_id()
        object_key = f"raw/{run_id}/{image_id}.{ext}"
        content_type = file.content_type or f"image/{ext}"

        try:
            storage_uri = storage_service.upload_file(
                file_content=file_bytes,
                object_name=object_key,
                content_type=content_type,
            )
        except Exception as e:
            logger.error(f"Storage upload failed for '{filename}': {e}")
            image_items.append(
                ImageUploadItem(
                    original_filename=filename,
                    format=ext,
                    file_size=size_bytes,
                    upload_status="failed",
                    error_message="STORAGE_UPLOAD_FAILED",
                )
            )
            failed_count += 1
            continue

        # ── Persist metadata ─────────────────
        upload_order = upload_order_base + uploaded_count + 1
        image_record = Image(
            id=image_id,
            run_id=run_id,
            original_filename=filename,
            storage_uri=storage_uri,
            width=width,
            height=height,
            format=ext,
            file_size=size_bytes,
            sha256_hash=sha256_hash,
            upload_order=upload_order,
            quality_status="pending_validation",
            is_valid=True,
        )
        db.add(image_record)
        uploaded_count += 1

        log_event("image_upload_completed", run_id=run_id, image_id=image_id)

        image_items.append(
            ImageUploadItem(
                image_id=image_id,
                original_filename=filename,
                format=ext,
                file_size=size_bytes,
                storage_uri=storage_uri,
                upload_status="success",
            )
        )

    # ── Update run counters ──────────────────
    if uploaded_count > 0:
        run.total_images = current_count + uploaded_count
        if run.status == "created":
            run.status = "uploading"

    await db.commit()

    return {
        "run_id": run_id,
        "uploaded_count": uploaded_count,
        "failed_count": failed_count,
        "image_items": image_items,
        "warnings": warnings,
    }


async def get_run_images(
    db: AsyncSession, 
    run_id: str, 
    quality_status: str | None = None,
    is_canonical: bool | None = None
) -> List[Image]:
    """Return images for a run, optionally filtered by quality_status or is_canonical."""
    # Ensure run exists
    run_result = await db.execute(select(Run).where(Run.id == run_id))
    if not run_result.scalar_one_or_none():
        raise RunNotFoundException(run_id)

    query = select(Image).where(Image.run_id == run_id)
    if quality_status:
        query = query.where(Image.quality_status == quality_status)
    if is_canonical is not None:
        query = query.where(Image.is_canonical == is_canonical)
    query = query.order_by(Image.upload_order.asc())

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_artifact_by_type(db: AsyncSession, run_id: str, artifact_type: str) -> Any | None:
    """Fetch an artifact for a run by its type."""
    from app.db.models.artifact import Artifact
    art_result = await db.execute(
        select(Artifact)
        .where(Artifact.run_id == run_id)
        .where(Artifact.artifact_type == artifact_type)
        .order_by(Artifact.created_at.desc())
    )
    return art_result.scalar_one_or_none()


async def get_preprocessing_report(db: AsyncSession, run_id: str) -> dict | None:
    """
    Fetch the image_quality_report.json artifact for a run.
    Returns the parsed JSON dict or None if not available yet.
    """
    from app.db.models.artifact import Artifact
    import json

    run_result = await db.execute(select(Run).where(Run.id == run_id))
    if not run_result.scalar_one_or_none():
        raise RunNotFoundException(run_id)

    art_result = await db.execute(
        select(Artifact)
        .where(Artifact.run_id == run_id)
        .where(Artifact.artifact_type == "image_quality_report")
        .order_by(Artifact.created_at.desc())
    )
    artifact = art_result.scalar_one_or_none()
    if not artifact or not artifact.storage_uri:
        return None

    # Download from storage
    from app.services.storage_service import storage_service
    object_key = artifact.storage_uri.replace(f"s3://{storage_service.bucket_name}/", "")
    try:
        data = storage_service.download_file(object_key)
        return json.loads(data)
    except Exception:
        return None


def get_image_thumbnail_url(image: Image, expiration: int = 3600) -> str | None:
    """Generate a presigned URL for the image's thumbnail."""
    if not image.thumbnail_uri:
        return None
    object_key = image.thumbnail_uri.replace(f"s3://{storage_service.bucket_name}/", "")
    return storage_service.get_presigned_url(object_key, expiration=expiration)

