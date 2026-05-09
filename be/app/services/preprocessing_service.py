"""
Preprocessing Service — Image quality validation, normalization, thumbnail generation.

Orchestrates: raw image load → decode check → viewport → quality → type → noise
              → normalize → thumbnail → status update → quality report.
"""
import json
import uuid
import time
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

import cv2
import numpy as np
from PIL import Image as PILImage

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger, log_event
from app.db.models.run import Run
from app.db.models.image import Image
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service


# ──────────────────────────────────────────────
# Constants & thresholds
# ──────────────────────────────────────────────

THUMBNAIL_WIDTH = 360
THUMBNAIL_HEIGHT = 225

# Laplacian variance thresholds for blur detection
BLUR_SHARP_THRESHOLD = 100.0
BLUR_WARNING_THRESHOLD = 50.0

# Brightness thresholds (0-255 mean pixel value)
BRIGHTNESS_TOO_DARK = 40.0
BRIGHTNESS_TOO_BRIGHT = 220.0

# Contrast threshold (std dev of grayscale)
CONTRAST_LOW_THRESHOLD = 30.0


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
) -> Tuple[Optional[PILImage.Image], Optional[np.ndarray], Dict[str, Any]]:
    """
    Attempt to decode image. Returns (pil_image, cv2_image, report_dict).
    If decode fails, pil_image and cv2_image are None.
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
        return None, None, report

    # Check format match
    detected_format = (pil_img.format or "").upper()
    format_map = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
    detected_ext = format_map.get(detected_format, detected_format.lower())

    if metadata_format and detected_ext != metadata_format:
        report["warning"] = f"IMAGE_METADATA_MISMATCH: expected {metadata_format}, got {detected_ext}"

    # Convert to cv2 (BGR numpy array)
    try:
        rgb = pil_img.convert("RGB")
        cv2_img = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
    except Exception as e:
        report["error"] = f"IMAGE_DECODE_FAILED: cv2 conversion error: {e}"
        return None, None, report

    report["passed"] = True
    report["actual_width"] = pil_img.width
    report["actual_height"] = pil_img.height
    return pil_img, cv2_img, report


# ──────────────────────────────────────────────
# Module 2.3 — Viewport Validation
# ──────────────────────────────────────────────

def _check_viewport(
    width: int, height: int, expected_w: int, expected_h: int
) -> Dict[str, Any]:
    """Strict viewport size check."""
    passed = (width == expected_w and height == expected_h)
    return {
        "expected_width": expected_w,
        "expected_height": expected_h,
        "actual_width": width,
        "actual_height": height,
        "passed": passed,
    }


# ──────────────────────────────────────────────
# Module 2.4 — Image Quality Validation
# ──────────────────────────────────────────────

def _check_quality(cv2_img: np.ndarray) -> Dict[str, Any]:
    """Compute blur, brightness, and contrast scores."""
    gray = cv2.cvtColor(cv2_img, cv2.COLOR_BGR2GRAY)

    # Blur: Laplacian variance
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

    if laplacian_var >= BLUR_SHARP_THRESHOLD:
        blur_status = "sharp"
    elif laplacian_var >= BLUR_WARNING_THRESHOLD:
        blur_status = "slightly_blurry"
    else:
        blur_status = "too_blurry"

    # Brightness: mean pixel intensity
    mean_brightness = float(np.mean(gray))
    if mean_brightness < BRIGHTNESS_TOO_DARK:
        brightness_status = "too_dark"
    elif mean_brightness > BRIGHTNESS_TOO_BRIGHT:
        brightness_status = "too_bright"
    else:
        brightness_status = "normal"

    # Contrast: std deviation of pixel intensity
    contrast = float(np.std(gray))
    contrast_status = "low_contrast" if contrast < CONTRAST_LOW_THRESHOLD else "normal"

    return {
        "blur_score": round(laplacian_var, 2),
        "blur_status": blur_status,
        "brightness_score": round(mean_brightness, 2),
        "brightness_status": brightness_status,
        "contrast_score": round(contrast, 2),
        "contrast_status": contrast_status,
        "readability_status": "readable",  # placeholder, upgraded in future with OCR
    }


# ──────────────────────────────────────────────
# Module 2.5 — Screenshot Type Validation
# ──────────────────────────────────────────────

def _check_screenshot_type(
    width: int, height: int, expected_w: int, expected_h: int
) -> Dict[str, Any]:
    """Heuristic screenshot type check based on dimensions."""
    if width == expected_w and height == expected_h:
        stype = "viewport_screenshot"
        passed = True
    elif height > expected_h * 2:
        stype = "full_page"
        passed = False
    elif width < expected_w * 0.5 or height < expected_h * 0.5:
        stype = "cropped_component"
        passed = False
    elif width > expected_w * 2:
        stype = "stitched"
        passed = False
    else:
        stype = "unknown"
        passed = False

    return {"type": stype, "passed": passed}


# ──────────────────────────────────────────────
# Module 2.6 — External Noise Detection (heuristic)
# ──────────────────────────────────────────────

def _check_external_noise(cv2_img: np.ndarray) -> Dict[str, Any]:
    """
    Lightweight heuristic noise detection.
    Checks for potential browser chrome (uniform strip at top).
    """
    noise_types: List[str] = []
    h, w = cv2_img.shape[:2]

    # Browser chrome heuristic: check if top ~80px is a uniform color bar
    if h > 100:
        top_strip = cv2_img[:80, :, :]
        top_std = float(np.std(top_strip))
        if top_std < 15:  # very uniform → possibly browser chrome
            noise_types.append("possible_browser_chrome")

    noise_detected = len(noise_types) > 0
    severity = "low" if noise_detected else "none"

    return {
        "noise_detected": noise_detected,
        "noise_types": noise_types,
        "severity": severity,
    }


# ──────────────────────────────────────────────
# Module 2.7 — Image Normalization
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
# Module 2.8 — Thumbnail Generation
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
# Module 2.10 — Quality Report Builder
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
        "too_blurry_count": sum(1 for r in results if r.get("quality_status") == "invalid_too_blurry"),
        "corrupted_count": sum(1 for r in results if r.get("quality_status") == "invalid_corrupted"),
        "full_page_count": sum(1 for r in results if r.get("quality_status") == "invalid_full_page"),
        "cropped_count": sum(1 for r in results if r.get("quality_status") == "invalid_cropped"),
        "stitched_count": sum(1 for r in results if r.get("quality_status") == "invalid_stitched_image"),
        "external_noise_count": sum(1 for r in results if r.get("quality_status") == "invalid_external_annotation"),
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

    config = run.config_json or {}
    expected_w = config.get("viewport_width", settings.REQUIRED_VIEWPORT_WIDTH)
    expected_h = config.get("viewport_height", settings.REQUIRED_VIEWPORT_HEIGHT)
    strict = config.get("strict_quality_validation", True)

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
        result = _process_single_image(img, run_id, expected_w, expected_h, strict)
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
    report = _build_quality_report(run_id, per_image_results)
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

def _process_single_image(
    img: Image,
    run_id: str,
    expected_w: int,
    expected_h: int,
    strict: bool,
) -> Dict[str, Any]:
    """Run all validation steps on a single image and return result dict."""
    result: Dict[str, Any] = {
        "image_id": img.id,
        "original_filename": img.original_filename,
        "is_valid": True,
        "quality_status": "valid",
        "invalid_reason": None,
        "normalized_uri": None,
        "thumbnail_uri": None,
        "warnings": [],
        "preprocessing_json": {},
    }

    # ── Step 1: Load raw image ───────────────
    log_event("image_loaded", run_id=run_id, image_id=img.id, node_name="image_preprocessing")
    raw_bytes, load_error = _load_raw_image(img)
    if load_error:
        result["is_valid"] = False
        result["quality_status"] = "invalid_corrupted"
        result["invalid_reason"] = load_error
        return result

    # ── Step 2: Decode & integrity ───────────
    pil_img, cv2_img, decode_report = _check_decode_integrity(raw_bytes, img.format)
    if pil_img is None or cv2_img is None:
        result["is_valid"] = False
        result["quality_status"] = "invalid_corrupted"
        result["invalid_reason"] = decode_report.get("error", "IMAGE_DECODE_FAILED")
        result["preprocessing_json"]["decode_check"] = decode_report
        return result

    if decode_report.get("warning"):
        result["warnings"].append(decode_report["warning"])

    actual_w = pil_img.width
    actual_h = pil_img.height

    # ── Step 3: Viewport validation ──────────
    viewport_result = _check_viewport(actual_w, actual_h, expected_w, expected_h)
    result["preprocessing_json"]["viewport_check"] = viewport_result

    if not viewport_result["passed"]:
        result["is_valid"] = False
        result["quality_status"] = "invalid_wrong_viewport"
        result["invalid_reason"] = (
            f"wrong viewport: expected {expected_w}x{expected_h}, got {actual_w}x{actual_h}"
        )
        result["preprocessing_json"]["quality_check"] = {}
        result["preprocessing_json"]["screenshot_type_check"] = {}
        result["preprocessing_json"]["noise_check"] = {}
        return result

    # ── Step 4: Quality validation ───────────
    quality_result = _check_quality(cv2_img)
    result["preprocessing_json"]["quality_check"] = quality_result

    if quality_result["blur_status"] == "too_blurry":
        result["is_valid"] = False
        result["quality_status"] = "invalid_too_blurry"
        result["invalid_reason"] = f"image is too blurry (score: {quality_result['blur_score']})"
        return result
    elif quality_result["blur_status"] == "slightly_blurry":
        result["warnings"].append(f"slightly blurry (score: {quality_result['blur_score']})")

    if quality_result["brightness_status"] in ("too_dark", "too_bright"):
        if strict:
            result["warnings"].append(f"brightness: {quality_result['brightness_status']}")
        else:
            result["warnings"].append(f"brightness: {quality_result['brightness_status']}")

    if quality_result["contrast_status"] == "low_contrast":
        result["warnings"].append(f"low contrast (score: {quality_result['contrast_score']})")

    # ── Step 5: Screenshot type ──────────────
    type_result = _check_screenshot_type(actual_w, actual_h, expected_w, expected_h)
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

    # ── Step 6: Noise detection ──────────────
    noise_result = _check_external_noise(cv2_img)
    result["preprocessing_json"]["noise_check"] = noise_result

    if noise_result["noise_detected"]:
        for nt in noise_result["noise_types"]:
            result["warnings"].append(f"noise detected: {nt}")

    # ── Step 7: Normalize ────────────────────
    norm_uri, norm_err = _normalize_image(pil_img, run_id, img.id)
    if norm_err:
        result["is_valid"] = False
        result["quality_status"] = "invalid_corrupted"
        result["invalid_reason"] = norm_err
        return result
    result["normalized_uri"] = norm_uri

    # ── Step 8: Thumbnail ────────────────────
    thumb_uri, thumb_err = _generate_thumbnail(pil_img, run_id, img.id)
    if thumb_err:
        result["warnings"].append(thumb_err)
    else:
        result["thumbnail_uri"] = thumb_uri

    # ── Final status ─────────────────────────
    if result["warnings"]:
        result["quality_status"] = "warning_low_quality"

    result["preprocessing_json"]["warnings"] = result["warnings"]

    return result
