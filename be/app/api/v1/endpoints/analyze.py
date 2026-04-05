import os
import uuid
import logging
from collections import deque
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query
from fastapi.responses import PlainTextResponse

from app.schemas.analysis import AnalysisRecordInDB
from app.core.config import settings
from app.core.exceptions import AIProcessingError

from .analyze_models import (
    AnalyzeByImageRequest,
    DefaultInputCreate,
    DefaultInputUpdate,
    PresignedUploadRequest,
    UploadSessionPayload,
)
from .analyze_utils import (
    b2_service,
    build_default_inputs_from_b2,
    cleanup_expired_data_if_needed,
    decode_default_input_id,
    download_remote_image,
    encode_default_input_id,
    extract_and_minify_json,
    get_b2_upload_prefix,
    is_user_upload_key,
    record_to_legacy_response,
    resolve_default_input_image_url,
    resolve_image_url_for_analysis,
    resolve_model_result,
    safe_file_extension,
    safe_remove_local_file,
    save_analysis_record_task,
    save_upload_file,
    supabase_service,
)

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/presigned-url")
def create_presigned_upload_url(payload: PresignedUploadRequest):
    cleanup_expired_data_if_needed()

    if not b2_service.s3_client:
        raise HTTPException(
            status_code=503,
            detail="B2 presigned upload is not configured on server.",
        )

    safe_ext = safe_file_extension(payload.file_name)
    prefix = get_b2_upload_prefix(payload.input_type)

    file_key = f"{prefix}/{uuid.uuid4()}.{safe_ext}"
    session_id = str(uuid.uuid4())

    try:
        # Generate presigned URL signed with content_type to match file upload
        upload_data = b2_service.generate_presigned_put_url(file_key, payload.file_type)
        if isinstance(upload_data, str):
            upload_url = upload_data
            headers = {}
            method = "PUT"
        else:
            upload_url = upload_data.get("upload_url")
            headers = upload_data.get("headers", {})
            method = upload_data.get("method", "PUT")
            
        file_url = b2_service.get_file_url(file_key)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to create presigned upload URL: {e}")
        raise HTTPException(status_code=500, detail="Could not create upload URL") from e

    # Add CORS headers to tell axios this is safe for cross-origin
    # Frontend will not add custom headers to avoid preflight
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "PUT, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }
    headers.update(cors_headers)

    return {
        "upload_url": upload_url,
        "file_url": file_url,
        "file_key": file_key,
        "session_id": session_id,
        "notify_url": "/api/v1/upload-session",
        "headers": headers,
        "method": method,
    }


@router.get("/logs/backend")
def read_backend_logs(lines: int = Query(200, ge=1, le=2000)):
    log_file_path = os.path.abspath("log.txt")

    if not os.path.exists(log_file_path):
        raise HTTPException(status_code=404, detail="Backend log file not found.")

    try:
        with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
            last_lines = list(deque(f, maxlen=lines))
        return {
            "lines": [line.rstrip("\n") for line in last_lines],
        }
    except Exception as e:
        logger.error(f"Failed to read backend logs: {e}")
        raise HTTPException(status_code=500, detail="Could not read backend logs.") from e

@router.post("/upload-to-b2")
async def upload_file_to_b2(
    file: UploadFile = File(...),
    input_type: str = Query("user", description="Upload target: 'user' or 'default'"),
):
    """
    Backend receives file and uploads to B2 (server-to-server, no CORS issues).
    Frontend must send with Content-Type: multipart/form-data
    Returns the B2 file URL for frontend to use.
    """
    cleanup_expired_data_if_needed()

    if not b2_service.s3_client:
        raise HTTPException(
            status_code=503,
            detail="B2 service is not configured on server.",
        )

    normalized_input_type = (input_type or "user").strip().lower()
    if normalized_input_type not in {"user", "default"}:
        raise HTTPException(status_code=400, detail="input_type must be 'user' or 'default'")

    # Save file temporarily
    temp_file_path = save_upload_file(file)

    try:
        # Upload to B2 with proper content type metadata
        safe_ext = safe_file_extension(file.filename or "file")
        prefix = get_b2_upload_prefix(normalized_input_type)

        b2_file_name = f"{prefix}/{uuid.uuid4()}.{safe_ext}"

        b2_service.upload_file(temp_file_path, b2_file_name, file.content_type)
        file_url = b2_service.get_file_url(b2_file_name)

        logger.info(f"Successfully uploaded {b2_file_name} (content_type: {file.content_type})")

        return {
            "file_url": file_url,
            "file_key": b2_file_name,
        }
    except Exception as e:
        logger.error(f"Failed to upload to B2: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to upload to B2: {str(e)}")
    finally:
        safe_remove_local_file(temp_file_path)


@router.post("/upload-session")
def save_upload_session(payload: UploadSessionPayload):
    cleanup_expired_data_if_needed()
    logger.debug("Received upload session notification for session_id=%s", payload.session_id)
    return {"ok": True}


@router.post("/api/analyze")
async def analyze_by_image_url(payload: AnalyzeByImageRequest):
    cleanup_expired_data_if_needed()

    if not payload.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    analysis_image_url = resolve_image_url_for_analysis(
        payload.image_url,
        payload.file_key,
    )
    file_path = download_remote_image(analysis_image_url)

    try:
        scenario_result = resolve_model_result(file_path, payload.model)
    except AIProcessingError as e:
        safe_remove_local_file(file_path)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        safe_remove_local_file(file_path)
        logger.error(f"Internal Server Error during URL analysis: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during analysis")

    cleaned_scenario_json = extract_and_minify_json(scenario_result)
    if cleaned_scenario_json and supabase_service.is_ready():
        try:
            supabase_service.create_analysis_record(
                image_url=payload.image_url,
                user_goal=cleaned_scenario_json,
            )
        except Exception as e:
            logger.error(f"Could not save URL analysis record to Supabase: {e}")

    safe_remove_local_file(file_path)

    return PlainTextResponse(content=scenario_result)


@router.post("/analyze")
async def analyze_screenshot(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: Optional[str] = Query("gemini-2.5-flash", description="Model to use: 'openai', 'gemini', 'gemini-2.5-flash', 'gemini-1.5-flash'")
):
    cleanup_expired_data_if_needed()

    # 1. Save the uploaded file to a temporary local path for processing
    file_path = save_upload_file(file)

    # 2. Call AI Service with the local file path
    try:
        scenario_result = resolve_model_result(file_path, model)

    except AIProcessingError as e:
        # Clean up file if AI fails
        safe_remove_local_file(file_path)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        safe_remove_local_file(file_path)
        logger.error(f"Internal Server Error during analysis: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during analysis")

    # 3. Trigger Background Task for Persistence
    background_tasks.add_task(save_analysis_record_task, file_path, scenario_result)

    # 4. Return the raw result as plain text
    return PlainTextResponse(content=scenario_result)

@router.get("/records", response_model=List[AnalysisRecordInDB])
def read_records(
    skip: int = 0,
    limit: int = 100
):
    """
    Retrieve all analysis records.
    """
    cleanup_expired_data_if_needed()

    if not supabase_service.is_ready():
        raise HTTPException(status_code=503, detail="Supabase is not configured on server.")

    records = supabase_service.get_analysis_records(skip=skip, limit=limit)
    return [record_to_legacy_response(record) for record in records]

@router.delete("/records/{record_id}", response_model=AnalysisRecordInDB)
def delete_record(
    record_id: int
):
    """
    Delete an analysis record by ID.
    """
    cleanup_expired_data_if_needed()

    if not supabase_service.is_ready():
        raise HTTPException(status_code=503, detail="Supabase is not configured on server.")

    deleted = supabase_service.delete_analysis_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")

    key = b2_service.extract_key_from_url(str(deleted.get("image_url", "")))
    if is_user_upload_key(key):
        b2_service.delete_file(key)

    return record_to_legacy_response(deleted)


@router.get("/api/defaults")
def read_default_inputs():
    cleanup_expired_data_if_needed()

    if not b2_service.is_ready():
        raise HTTPException(status_code=503, detail="B2 service is not configured on server.")

    items = build_default_inputs_from_b2()
    return {"items": items}


@router.post("/api/defaults")
def create_default_input(payload: DefaultInputCreate):
    cleanup_expired_data_if_needed()

    file_key = payload.file_key
    if not file_key and payload.image_url:
        file_key = b2_service.extract_key_from_url(payload.image_url)

    if not file_key:
        raise HTTPException(status_code=400, detail="file_key or valid image_url is required")

    default_prefix = settings.B2_DEFAULT_INPUTS_PREFIX.strip("/")
    if not str(file_key).startswith(f"{default_prefix}/"):
        raise HTTPException(
            status_code=400,
            detail="file_key must be under B2_DEFAULT_INPUTS_PREFIX",
        )

    return {
        "id": encode_default_input_id(file_key),
        "image_url": resolve_default_input_image_url(file_key),
        "file_key": file_key,
    }


@router.put("/api/defaults/{item_id}")
def update_default_input(item_id: str, payload: DefaultInputUpdate):
    cleanup_expired_data_if_needed()

    file_key = payload.file_key or decode_default_input_id(item_id)
    if not file_key:
        raise HTTPException(status_code=404, detail="Default input not found")

    default_prefix = settings.B2_DEFAULT_INPUTS_PREFIX.strip("/")
    if not str(file_key).startswith(f"{default_prefix}/"):
        raise HTTPException(
            status_code=400,
            detail="file_key must be under B2_DEFAULT_INPUTS_PREFIX",
        )

    image_url = payload.image_url or resolve_default_input_image_url(file_key)

    return {
        "id": encode_default_input_id(file_key),
        "image_url": image_url,
        "file_key": file_key,
    }


@router.delete("/api/defaults/{item_id}")
def delete_default_input(item_id: str):
    cleanup_expired_data_if_needed()

    if not b2_service.is_ready():
        raise HTTPException(status_code=503, detail="B2 service is not configured on server.")

    file_key = decode_default_input_id(item_id)
    if not file_key:
        raise HTTPException(status_code=404, detail="Default input not found")

    if not str(file_key).startswith(f"{settings.B2_DEFAULT_INPUTS_PREFIX}/"):
        raise HTTPException(status_code=400, detail="Invalid default input key")

    deleted = b2_service.delete_file(str(file_key))
    if not deleted:
        raise HTTPException(status_code=404, detail="Default input not found")

    return {"id": item_id, "file_key": file_key, "deleted": True}
