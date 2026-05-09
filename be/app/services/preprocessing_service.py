"""
Preprocessing Service — Image decode, viewport checks, normalization, thumbnail generation.

Orchestrates: raw image load → decode check → viewport aspect bands → screenshot type
              → normalize → thumbnail → status update → quality report.
"""
import json
import uuid
import time
from dataclasses import dataclass
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from PIL import Image as PILImage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event
from app.db.models.run import Run
from app.db.models.image import Image
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service


# ──────────────────────────────────────────────
# Constants & thresholds
# ──────────────────────────────────────────────

THUMBNAIL_WIDTH = 360
THUMBNAIL_HEIGHT = 225


@dataclass(frozen=True)
class ViewportBandConfig:
    """Orientation-invariant viewport constraints: long=max(w,h), short=min(w,h)."""

    short_edge_min: int
    short_edge_max: int
    long_edge_min: int
    long_edge_max: int
    aspect_ratio_min: float
    aspect_ratio_max: float


def viewport_bands_from_settings() -> ViewportBandConfig:
    return ViewportBandConfig(
        short_edge_min=settings.VIEWPORT_SHORT_EDGE_MIN,
        short_edge_max=settings.VIEWPORT_SHORT_EDGE_MAX,
        long_edge_min=settings.VIEWPORT_LONG_EDGE_MIN,
        long_edge_max=settings.VIEWPORT_LONG_EDGE_MAX,
        aspect_ratio_min=settings.VIEWPORT_ASPECT_RATIO_MIN,
        aspect_ratio_max=settings.VIEWPORT_ASPECT_RATIO_MAX,
    )


def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


# ──────────────────────────────────────────────
# Helper: extract object key from s3:// URI
# ──────────────────────────────────────────────

def _uri_to_key(storage_uri: str) -> str:
    """Convert s3://bucket/key to just key."""
    # s3://ui-testgen-local/raw/run_xxx/img_xxx.png → raw/run_xxx/img_xxx.png
    parts = storage_uri.replace("s3://", "").split("/", 1)
    return parts[1] if len(parts) > 1 else storage_uri


# ──────────────────────────────────────────────
# Module 2.1 — Raw Image Loader
# ──────────────────────────────────────────────

def _load_raw_image(image: Image) -> Tuple[Optional[bytes], Optional[str]]:
    """Download raw image bytes from storage. Returns (bytes, error_string)."""
    if not image.storage_uri:
        return None, "RAW_IMAGE_NOT_FOUND: no storage_uri"

    object_key = _uri_to_key(image.storage_uri)
    try:
        data = storage_service.download_file(object_key)
        return data, None
    except Exception as e:
        return None, f"RAW_IMAGE_NOT_FOUND: {e}"


# ──────────────────────────────────────────────
# Module 2.2 — Image Decode & Integrity Check
# ──────────────────────────────────────────────

def _check_decode_integrity(
    image_bytes: bytes, metadata_format: Optional[str]
) -> Tuple[Optional[PILImage.Image], Dict[str, Any]]:
    """
    Attempt to decode image. Returns (pil_image, report_dict).
    """
    report: Dict[str, Any] = {"passed": False}

    try:
        pil_img = PILImage.open(BytesIO(image_bytes))
        pil_img.verify()
        # Re-open after verify
        pil_img = PILImage.open(BytesIO(image_bytes))
        pil_img.load()  # force full decode
    except Exception as e:
        report["error"] = f"IMAGE_DECODE_FAILED: {e}"
        return None, report

    # Check format match
    detected_format = (pil_img.format or "").upper()
    format_map = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
    detected_ext = format_map.get(detected_format, detected_format.lower())

    if metadata_format and detected_ext != metadata_format:
        report["warning"] = f"IMAGE_METADATA_MISMATCH: expected {metadata_format}, got {detected_ext}"

    report["passed"] = True
    report["actual_width"] = pil_img.width
    report["actual_height"] = pil_img.height
    return pil_img, report


# ──────────────────────────────────────────────
# Module 2.3 — Viewport Validation (edge bands + aspect ratio)
# ──────────────────────────────────────────────

def _check_viewport_aspect_bands(
    width: int, height: int, bands: ViewportBandConfig
) -> Dict[str, Any]:
    """
    long = max(w,h), short = min(w,h). Pass when all band rules hold.
    """
    long_side = max(width, height)
    short_side = min(width, height)
    ratio = (long_side / short_side) if short_side > 0 else 0.0
    failure_reasons: List[str] = []

    if not (bands.long_edge_min <= long_side <= bands.long_edge_max):
        failure_reasons.append(
            f"long_side {long_side} not in [{bands.long_edge_min}, {bands.long_edge_max}]"
        )
    if not (bands.short_edge_min <= short_side <= bands.short_edge_max):
        failure_reasons.append(
            f"short_side {short_side} not in [{bands.short_edge_min}, {bands.short_edge_max}]"
        )
    if not (bands.aspect_ratio_min <= ratio <= bands.aspect_ratio_max):
        failure_reasons.append(
            f"aspect_ratio {ratio:.4f} not in [{bands.aspect_ratio_min}, {bands.aspect_ratio_max}]"
        )

    passed = len(failure_reasons) == 0
    return {
        "actual_width": width,
        "actual_height": height,
        "long_side": long_side,
        "short_side": short_side,
        "ratio": round(ratio, 4),
        "thresholds": {
            "short_edge_min": bands.short_edge_min,
            "short_edge_max": bands.short_edge_max,
            "long_edge_min": bands.long_edge_min,
            "long_edge_max": bands.long_edge_max,
            "aspect_ratio_min": bands.aspect_ratio_min,
            "aspect_ratio_max": bands.aspect_ratio_max,
        },
        "failure_reasons": failure_reasons,
        "passed": passed,
    }


# ──────────────────────────────────────────────
# Module 2.4 — Screenshot Type Validation
# ──────────────────────────────────────────────

def _check_screenshot_type(
    width: int, height: int, _bands: ViewportBandConfig
) -> Dict[str, Any]:
    """Runs after viewport bands passed — classify as viewport capture (constraints enforced upstream)."""
    long_side = max(width, height)
    short_side = min(width, height)
    ratio = long_side / short_side if short_side > 0 else 0.0
    return {
        "type": "viewport_screenshot",
        "passed": True,
        "long_side": long_side,
        "short_side": short_side,
        "ratio": round(ratio, 4),
    }


# ──────────────────────────────────────────────
# Module 2.5 — Image Normalization
# ──────────────────────────────────────────────

def _normalize_image(pil_img: PILImage.Image, run_id: str, image_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Convert to RGB, strip metadata, save as PNG. Returns (storage_uri, error)."""
    try:
        rgb = pil_img.convert("RGB")
        buf = BytesIO()
        rgb.save(buf, format="PNG")
        buf.seek(0)
        data = buf.getvalue()

        object_key = f"normalized/{run_id}/{image_id}.png"
        uri = storage_service.upload_file(data, object_key, content_type="image/png")
        return uri, None
    except Exception as e:
        return None, f"NORMALIZATION_FAILED: {e}"


# ──────────────────────────────────────────────
# Module 2.6 — Thumbnail Generation
# ──────────────────────────────────────────────

def _generate_thumbnail(pil_img: PILImage.Image, run_id: str, image_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Resize to thumbnail and save as WebP. Returns (storage_uri, error)."""
    try:
        rgb = pil_img.convert("RGB")
        rgb.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), PILImage.Resampling.LANCZOS)
        buf = BytesIO()
        rgb.save(buf, format="WEBP", quality=80)
        buf.seek(0)

        object_key = f"thumbnail/{run_id}/{image_id}.webp"
        uri = storage_service.upload_file(buf.getvalue(), object_key, content_type="image/webp")
        return uri, None
    except Exception as e:
        return None, f"THUMBNAIL_GENERATION_FAILED: {e}"


# ──────────────────────────────────────────────
# Module 2.7 — Quality Report Builder
# ──────────────────────────────────────────────

def _build_quality_report(
    run_id: str,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the image_quality_report.json from per-image results."""
    valid_ids = [r["image_id"] for r in results if r["is_valid"]]
    invalid_items = [
        {
            "image_id": r["image_id"],
            "reason": r.get("invalid_reason", ""),
            "quality_status": r.get("quality_status", ""),
        }
        for r in results if not r["is_valid"]
    ]
    warning_items = [
        {
            "image_id": r["image_id"],
            "warnings": r.get("warnings", []),
        }
        for r in results if r.get("warnings")
    ]

    # Summary counts
    summary = {
        "wrong_viewport_count": sum(1 for r in results if r.get("quality_status") == "invalid_wrong_viewport"),
        "corrupted_count": sum(1 for r in results if r.get("quality_status") == "invalid_corrupted"),
        "full_page_count": sum(1 for r in results if r.get("quality_status") == "invalid_full_page"),
        "cropped_count": sum(1 for r in results if r.get("quality_status") == "invalid_cropped"),
        "stitched_count": sum(1 for r in results if r.get("quality_status") == "invalid_stitched_image"),
    }

    return {
        "run_id": run_id,
        "total_images": len(results),
        "processed_images": len(results),
        "valid_images": len(valid_ids),
        "invalid_images": len(invalid_items),
        "valid_image_ids": valid_ids,
        "invalid_items": invalid_items,
        "warning_items": warning_items,
        "summary": summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def build_quality_report(run_id: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Public wrapper for assembling image_quality_report.json from per-image result dicts."""
    return _build_quality_report(run_id, results)


# ══════════════════════════════════════════════
# Main orchestrator
# ══════════════════════════════════════════════

async def run_preprocessing(db: AsyncSession, run_id: str) -> Dict[str, Any]:
    """
    Execute the full image preprocessing pipeline for a run.

    Returns a dict with keys: valid_images, invalid_images, report, errors.
    """
    start_time = time.time()
    log_event("image_preprocessing_started", run_id=run_id, node_name="image_preprocessing")

    # ── Load run and config ──────────────────
    run_result = await db.execute(select(Run).where(Run.id == run_id))
    run = run_result.scalar_one_or_none()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    bands = viewport_bands_from_settings()

    # ── Load image records ───────────────────
    img_result = await db.execute(
        select(Image)
        .where(Image.run_id == run_id)
        .order_by(Image.upload_order.asc())
    )
    images = list(img_result.scalars().all())

    per_image_results: List[Dict[str, Any]] = []
    valid_count = 0
    invalid_count = 0

    for img in images:
        result = _process_single_image(img, run_id, bands)
        per_image_results.append(result)

        # ── Update DB record (Module 2.9) ────
        img.quality_status = result["quality_status"]
        img.is_valid = result["is_valid"]
        img.invalid_reason = result.get("invalid_reason")
        img.normalized_uri = result.get("normalized_uri")
        img.thumbnail_uri = result.get("thumbnail_uri")
        img.preprocessing_json = result.get("preprocessing_json")

        if result["is_valid"]:
            valid_count += 1
            log_event("image_normalized", run_id=run_id, image_id=img.id, node_name="image_preprocessing")
        else:
            invalid_count += 1
            log_event("image_marked_invalid", run_id=run_id, image_id=img.id,
                       node_name="image_preprocessing", error_code=result.get("quality_status"))

    # ── Update run counters ──────────────────
    run.valid_images = valid_count
    run.invalid_images = invalid_count

    # ── Build & save quality report ──────────
    report = build_quality_report(run_id, per_image_results)
    report_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
    report_key = f"artifacts/{run_id}/image_preprocessing/image_quality_report.json"
    report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

    artifact = Artifact(
        id=_generate_artifact_id(),
        run_id=run_id,
        artifact_type="image_quality_report",
        node_name="image_preprocessing",
        storage_uri=report_uri,
        metadata_json={"valid_images": valid_count, "invalid_images": invalid_count},
    )
    db.add(artifact)

    # ── Handle no valid images ───────────────
    if valid_count == 0:
        run.status = "failed"
        run.error_message = "NO_VALID_IMAGES"
        log_event("image_preprocessing_failed", run_id=run_id,
                   node_name="image_preprocessing", error_code="NO_VALID_IMAGES")

    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("image_preprocessing_completed", run_id=run_id,
               node_name="image_preprocessing", duration_ms=duration_ms)

    return {
        "valid_images": [r for r in per_image_results if r["is_valid"]],
        "invalid_images": [r for r in per_image_results if not r["is_valid"]],
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "report": report,
        "errors": [],
    }


# ──────────────────────────────────────────────
# Per-image processing pipeline
# ──────────────────────────────────────────────

def run_preprocessing_pipeline_on_bytes(
    raw_bytes: bytes,
    *,
    image_id: str,
    original_filename: str,
    metadata_format: Optional[str],
    run_id: str,
    bands: ViewportBandConfig,
) -> Dict[str, Any]:
    """
    Decode, validate viewport, screenshot type label, normalize, and thumbnail from raw bytes.
    Same shape as _process_single_image result dict (no DB / storage download).
    """
    result: Dict[str, Any] = {
        "image_id": image_id,
        "original_filename": original_filename,
        "is_valid": True,
        "quality_status": "valid",
        "invalid_reason": None,
        "normalized_uri": None,
        "thumbnail_uri": None,
        "warnings": [],
        "preprocessing_json": {},
    }

    # ── Decode & integrity ───────────
    pil_img, decode_report = _check_decode_integrity(raw_bytes, metadata_format)
    if pil_img is None:
        result["is_valid"] = False
        result["quality_status"] = "invalid_corrupted"
        result["invalid_reason"] = decode_report.get("error", "IMAGE_DECODE_FAILED")
        result["preprocessing_json"]["decode_check"] = decode_report
        return result

    if decode_report.get("warning"):
        result["warnings"].append(decode_report["warning"])

    actual_w = pil_img.width
    actual_h = pil_img.height

    # ── Viewport validation ──────────
    viewport_result = _check_viewport_aspect_bands(actual_w, actual_h, bands)
    result["preprocessing_json"]["viewport_check"] = viewport_result

    if not viewport_result["passed"]:
        result["is_valid"] = False
        result["quality_status"] = "invalid_wrong_viewport"
        errs = viewport_result.get("failure_reasons") or []
        result["invalid_reason"] = "; ".join(errs) if errs else "viewport constraints not satisfied"
        return result

    # ── Screenshot type ──────────────
    type_result = _check_screenshot_type(actual_w, actual_h, bands)
    result["preprocessing_json"]["screenshot_type_check"] = type_result

    if not type_result["passed"]:
        type_to_status = {
            "full_page": "invalid_full_page",
            "cropped_component": "invalid_cropped",
            "stitched": "invalid_stitched_image",
        }
        result["is_valid"] = False
        result["quality_status"] = type_to_status.get(type_result["type"], "invalid_unreadable")
        result["invalid_reason"] = f"screenshot type: {type_result['type']}"
        return result

    # ── Normalize ────────────────────
    norm_uri, norm_err = _normalize_image(pil_img, run_id, image_id)
    if norm_err:
        result["is_valid"] = False
        result["quality_status"] = "invalid_corrupted"
        result["invalid_reason"] = norm_err
        return result
    result["normalized_uri"] = norm_uri

    # ── Thumbnail ────────────────────
    thumb_uri, thumb_err = _generate_thumbnail(pil_img, run_id, image_id)
    if thumb_err:
        result["warnings"].append(thumb_err)
    else:
        result["thumbnail_uri"] = thumb_uri

    # ── Final status ─────────────────────────
    if result["warnings"]:
        result["quality_status"] = "warning_low_quality"

    result["preprocessing_json"]["warnings"] = result["warnings"]

    return result


def _process_single_image(
    img: Image,
    run_id: str,
    bands: ViewportBandConfig,
) -> Dict[str, Any]:
    """Run all validation steps on a single image and return result dict."""
    log_event("image_loaded", run_id=run_id, image_id=img.id, node_name="image_preprocessing")
    raw_bytes, load_error = _load_raw_image(img)
    if load_error:
        return {
            "image_id": img.id,
            "original_filename": img.original_filename,
            "is_valid": False,
            "quality_status": "invalid_corrupted",
            "invalid_reason": load_error,
            "normalized_uri": None,
            "thumbnail_uri": None,
            "warnings": [],
            "preprocessing_json": {},
        }

    return run_preprocessing_pipeline_on_bytes(
        raw_bytes,
        image_id=img.id,
        original_filename=img.original_filename,
        metadata_format=img.format,
        run_id=run_id,
        bands=bands,
    )
