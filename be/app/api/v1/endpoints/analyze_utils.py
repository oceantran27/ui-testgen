import base64
import logging
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, UploadFile

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.services.b2_service import B2Service
from app.services.gemini_service import GeminiService
from app.services.openai_service import OpenAIService
from app.services.supabase_service import SupabaseService

from .json_utils import extract_and_minify_json

logger = logging.getLogger(__name__)

openai_service = OpenAIService()

try:
    gemini_service = GeminiService()
except Exception as exc:
    # Keep API process alive and report configuration issues when Gemini is requested.
    logger.warning("Gemini service unavailable during startup: %s", exc)
    gemini_service = None

b2_service = B2Service()
supabase_service = SupabaseService()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
_cleanup_lock = threading.Lock()
_cleanup_state = {"last_run": None}


def safe_file_extension(file_name: str, fallback: str = "bin") -> str:
    sanitized_name = (file_name or "").split("?", 1)[0].split("#", 1)[0]
    _, ext = os.path.splitext(sanitized_name)
    normalized = ext.lstrip(".").strip().lower()
    if not normalized:
        return fallback
    return re.sub(r"[^a-z0-9]", "", normalized) or fallback


def get_b2_upload_prefix(input_type: str | None) -> str:
    normalized_input_type = (input_type or "user").strip().lower()
    if normalized_input_type == "default":
        return settings.B2_DEFAULT_INPUTS_PREFIX
    return settings.B2_USER_INPUTS_PREFIX


def safe_remove_local_file(file_path: str) -> None:
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass


def save_upload_file(file: UploadFile) -> str:
    file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
    file_name = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return file_path
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not save image: {str(exc)}")


def download_remote_image(image_url: str) -> str:
    safe_ext = safe_file_extension(image_url, fallback="jpg")
    file_name = f"{uuid.uuid4()}.{safe_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(image_url)
            response.raise_for_status()

        with open(file_path, "wb") as output_file:
            output_file.write(response.content)

        return file_path
    except Exception as exc:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        raise HTTPException(status_code=400, detail=f"Could not download image: {exc}")


def resolve_model_result(file_path: str, model: str | None) -> str:
    selected_model = (model or "gemini-2.5-flash").strip().lower()

    if selected_model == "openai":
        return openai_service.analyze_image(file_path)
    if selected_model in {"gemini", "gemini-2.5-flash"}:
        if gemini_service is None:
            raise AIProcessingError("Gemini service is not configured. Please set GEMINI_API_KEY.")
        return gemini_service.analyze_image(file_path)
    if selected_model == "gemini-1.5-flash":
        if not settings.GEMINI_API_KEY:
            raise AIProcessingError("Gemini service is not configured. Please set GEMINI_API_KEY.")
        temp_service = GeminiService(model_name="gemini-1.5-flash")
        return temp_service.analyze_image(file_path)

    if gemini_service is None:
        raise AIProcessingError("Gemini service is not configured. Please set GEMINI_API_KEY.")
    return gemini_service.analyze_image(file_path)


def record_to_legacy_response(record: dict) -> dict:
    image_url = str(record.get("image_url", ""))
    user_goal = str(record.get("user_goal", ""))
    return {
        "id": int(record.get("id", 0)),
        "image_path": resolve_analysis_record_image_url(image_url),
        "scenario_json": user_goal,
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def is_user_upload_key(file_key: str | None) -> bool:
    if not file_key:
        return False
    prefix = settings.B2_USER_INPUTS_PREFIX.strip("/")
    return file_key.startswith(f"{prefix}/")


def is_managed_b2_key(file_key: str | None) -> bool:
    if not file_key:
        return False

    normalized = str(file_key).strip()
    if not normalized:
        return False

    user_prefix = settings.B2_USER_INPUTS_PREFIX.strip("/")
    default_prefix = settings.B2_DEFAULT_INPUTS_PREFIX.strip("/")
    return normalized.startswith(f"{user_prefix}/") or normalized.startswith(f"{default_prefix}/")


def resolve_analysis_record_image_url(image_url: str) -> str:
    if not image_url:
        return image_url

    if not b2_service.is_ready():
        return image_url

    key = b2_service.extract_key_from_url(image_url)
    if not is_managed_b2_key(key):
        return image_url

    try:
        return b2_service.generate_presigned_get_url(str(key))
    except Exception as exc:
        logger.warning("Could not generate signed GET URL for record image %s: %s", image_url, exc)
        return image_url


def resolve_default_input_image_url(file_key: str) -> str:
    if not file_key:
        return ""

    raw_url = b2_service.get_file_url(file_key)
    if not b2_service.is_ready():
        return raw_url

    try:
        return b2_service.generate_presigned_get_url(file_key)
    except Exception as exc:
        logger.warning("Could not generate signed GET URL for default input %s: %s", file_key, exc)
        return raw_url


def resolve_image_url_for_analysis(image_url: str, file_key: str | None = None) -> str:
    if not image_url:
        return image_url

    if not b2_service.is_ready():
        return image_url

    key = file_key or b2_service.extract_key_from_url(image_url)
    if not is_managed_b2_key(key):
        return image_url

    try:
        return b2_service.generate_presigned_get_url(str(key))
    except Exception as exc:
        logger.warning(
            "Could not refresh signed URL for analysis image %s: %s",
            image_url,
            exc,
        )
        return image_url


def encode_default_input_id(file_key: str) -> str:
    return base64.urlsafe_b64encode(file_key.encode("utf-8")).decode("ascii").rstrip("=")


def decode_default_input_id(item_id: str) -> str | None:
    if not item_id:
        return None
    try:
        padded = item_id + "=" * (-len(item_id) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def build_default_inputs_from_b2() -> list[dict]:
    if not b2_service.is_ready():
        return []

    keys = b2_service.list_keys(settings.B2_DEFAULT_INPUTS_PREFIX)
    items: list[dict] = []

    for key in keys:
        normalized_key = key.strip()
        if not normalized_key:
            continue

        image_url = resolve_default_input_image_url(normalized_key)
        items.append(
            {
                "id": encode_default_input_id(normalized_key),
                "image_url": image_url,
                "file_key": normalized_key,
            }
        )

    return items


def cleanup_expired_data_if_needed() -> None:
    retention_days = settings.DATA_RETENTION_DAYS
    now = datetime.now(timezone.utc)

    with _cleanup_lock:
        last_run: datetime | None = _cleanup_state["last_run"]
        if last_run and (now - last_run) < timedelta(minutes=30):
            return
        _cleanup_state["last_run"] = now

    if not supabase_service.is_ready():
        logger.warning("Skip cleanup because Supabase is not configured.")
        return

    deleted_records = supabase_service.delete_expired_analysis_records(retention_days)
    deleted_keys: list[str] = []

    for record in deleted_records:
        image_url = str(record.get("image_url", ""))
        key = b2_service.extract_key_from_url(image_url)
        if is_user_upload_key(key):
            deleted_keys.append(key)

    cutoff = now - timedelta(days=retention_days)
    orphan_keys = b2_service.list_keys(settings.B2_USER_INPUTS_PREFIX, older_than=cutoff)

    all_keys = sorted(set([*deleted_keys, *orphan_keys]))
    if all_keys:
        removed_count = b2_service.delete_files(all_keys)
        logger.info("Cleanup removed %s user-upload files from B2.", removed_count)


def save_analysis_record_task(image_path: str, scenario_result: str) -> None:
    try:
        cleaned_scenario_json = extract_and_minify_json(scenario_result)
        if not cleaned_scenario_json:
            logger.error("Skipping save: could not extract valid JSON from model output.")
            return

        if not b2_service.is_ready():
            logger.error("Skipping save: B2 service is not configured.")
            return
        if not supabase_service.is_ready():
            logger.error("Skipping save: Supabase service is not configured.")
            return

        safe_ext = safe_file_extension(os.path.basename(image_path), fallback="jpg")
        b2_key = f"{settings.B2_USER_INPUTS_PREFIX}/{uuid.uuid4()}.{safe_ext}"
        b2_service.upload_file(image_path, b2_key)
        image_url = b2_service.get_file_url(b2_key)

        supabase_service.create_analysis_record(image_url=image_url, user_goal=cleaned_scenario_json)
        logger.info("Successfully saved analysis record for %s", image_url)
    except Exception as exc:
        logger.error("Failed to save analysis record in background: %s", exc)
    finally:
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                logger.warning("Could not remove temp file after background save: %s", image_path)
