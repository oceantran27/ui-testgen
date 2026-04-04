import shutil
import os
import uuid
import logging
import json
import re
import threading
from collections import deque
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Query
from fastapi.responses import PlainTextResponse
from typing import List, Optional, Any
from pydantic import BaseModel

from app.services.openai_service import OpenAIService
from app.services.gemini_service import GeminiService
from app.services.storage_service import StorageService
from app.services.b2_service import B2Service
from app.schemas.analysis import AnalysisRecordInDB
from app.core.exceptions import AIProcessingError

router = APIRouter()
openai_service = OpenAIService()
gemini_service = GeminiService()
logger = logging.getLogger(__name__)
b2_service = B2Service()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
RECORDS_B2_KEY = "data/analysis_records.json"
_records_lock = threading.Lock()

class PresignedUploadRequest(BaseModel):
    file_name: str
    file_type: str
    file_size: int

class UploadSessionRequest(BaseModel):
    session_id: Optional[str] = None
    file_key: Optional[str] = None
    file_url: str
    original_name: str
    content_type: Optional[str] = None
    size: Optional[int] = None

def _load_records() -> list[dict[str, Any]]:
    try:
        data = b2_service.get_json_file(RECORDS_B2_KEY)
        if isinstance(data, list):
            return data
        if data is None:
            return []
        logger.warning("Records file has invalid format. Resetting to empty list.")
        return []
    except Exception as e:
        logger.error(f"Could not read records file from B2: {e}")
        return []

def _save_records(records: list[dict[str, Any]]) -> None:
    try:
        success = b2_service.put_json_file(RECORDS_B2_KEY, records)
        if not success:
            logger.error("Failed to save records file to B2.")
    except Exception as e:
        logger.error(f"Error saving records file to B2: {e}")


def _next_record_id(records: list[dict[str, Any]]) -> int:
    if not records:
        return 1
    return max(int(record.get("id", 0)) for record in records) + 1


def _safe_file_extension(file_name: str, fallback: str = "bin") -> str:
    _, ext = os.path.splitext(file_name)
    normalized = ext.lstrip(".").strip().lower()
    if not normalized:
        return fallback
    return re.sub(r"[^a-z0-9]", "", normalized) or fallback

def _strip_json_comments(s: str) -> str:
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    s = re.sub(r"(^|\s)//.*$", "", s, flags=re.MULTILINE)
    return s


def _remove_trailing_commas(s: str) -> str:
    s = re.sub(r",\s*(?=[}\]])", "", s)
    return s


def _find_json_block(s: str) -> str | None:
    """Try multiple strategies to extract the JSON block from mixed output.
    Priority:
    1) Code fence labeled as json: ```json ... ```
    2) Any code fence content that looks like JSON (starts with { or [)
    3) Anchor by key '"user_intents"' and brace-match
    4) Brace-match from first '{'
    """
    lower = s.lower()

    # 1) Labeled json fence
    fence_labeled = "```json"
    start = lower.find(fence_labeled)
    if start != -1:
        start += len(fence_labeled)
        end = lower.find("```", start)
        if end != -1:
            block = s[start:end].strip()
            if block:
                return block

    # 2) Any code fence; choose the one that looks like JSON
    # Matches ```json\n...``` or ```\n...``` (case-insensitive for json)
    for_match = re.finditer(r"```(?:json)?\s*\n(.*?)```", s, flags=re.DOTALL | re.IGNORECASE)
    candidates: list[str] = []
    for m in for_match:
        content = m.group(1).strip()
        if content:
            candidates.append(content)
    # Prefer those starting with { or [ and containing a colon to indicate object/array
    jsonish = [c for c in candidates if (c.startswith("{") or c.startswith("[")) and ":" in c]
    if jsonish:
        return jsonish[-1]  # often the last fenced block is the Final JSON

    # 3) Anchor by likely top-level key
    key = '"user_intents"'
    key_idx = s.find(key)
    if key_idx != -1:
        i = s.rfind("{", 0, key_idx)
        if i != -1:
            depth = 0
            in_str = False
            esc = False
            for j in range(i, len(s)):
                ch = s[j]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            return s[i:j+1].strip()

    # 4) Fallback: first '{' with brace matching
    i = s.find("{")
    if i == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(i, len(s)):
        ch = s[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return s[i:j+1].strip()
    return None


def _extract_and_minify_json(s: str) -> str | None:
    """Return compact JSON string if extraction and parsing succeeds; otherwise None."""
    raw_json = _find_json_block(s)
    candidate = raw_json if raw_json is not None else s.strip()
    cleaned = _strip_json_comments(candidate)
    cleaned = _remove_trailing_commas(cleaned)
    try:
        parsed = json.loads(cleaned)
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        logger.error(f"Failed to parse extracted JSON: {e}")
        return None


def save_analysis_record_task(image_path: str, scenario_result: str):
    """
    Background task to persist the analysis record to local JSON storage.
    This task also handles moving the image to its final storage location (e.g., B2).
    """
    try:
        cleaned_scenario_json = _extract_and_minify_json(scenario_result)
        if not cleaned_scenario_json:
            logger.error("Skipping save: could not extract valid JSON from model output.")
            return

        # Process file for final storage based on STORAGE_TYPE.
        storage_service = StorageService()
        final_image_path = storage_service.process_local_file(image_path)

        now = datetime.now(timezone.utc).isoformat()
        with _records_lock:
            records = _load_records()
            record = {
                "id": _next_record_id(records),
                "image_path": final_image_path,
                "scenario_json": cleaned_scenario_json,
                "created_at": now,
                "updated_at": None,
            }
            records.append(record)
            _save_records(records)

        logger.info(f"Successfully saved analysis record for {final_image_path}")
    except Exception as e:
        logger.error(f"Failed to save analysis record in background: {e}")


@router.post("/presigned-url")
def create_presigned_upload_url(payload: PresignedUploadRequest):
    if not b2_service.s3_client:
        raise HTTPException(
            status_code=503,
            detail="B2 presigned upload is not configured on server.",
        )

    safe_ext = _safe_file_extension(payload.file_name)
    file_key = f"uploads/{uuid.uuid4()}.{safe_ext}"
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


@router.post("/upload-session")
def finalize_upload_session(payload: UploadSessionRequest):
    # Frontend expects this callback endpoint after direct PUT to B2.
    # For now we acknowledge payload and keep data flow consistent.
    return {
        "ok": True,
        "session_id": payload.session_id,
        "file_key": payload.file_key,
        "file_url": payload.file_url,
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
    file: UploadFile = File(...)
):
    """
    Backend receives file and uploads to B2 (server-to-server, no CORS issues).
    Frontend must send with Content-Type: multipart/form-data
    Returns the B2 file URL for frontend to use.
    """
    if not b2_service.s3_client:
        raise HTTPException(
            status_code=503,
            detail="B2 service is not configured on server.",
        )

    # Validate Content-Type is multipart form data
    content_type = file.content_type
    
    # Save file temporarily
    file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
    temp_file_name = f"{uuid.uuid4()}.{file_extension}"
    temp_file_path = os.path.join(UPLOAD_DIR, temp_file_name)

    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Upload to B2 with proper content type metadata
        safe_ext = _safe_file_extension(file.filename or "file")
        b2_file_name = f"uploads/{uuid.uuid4()}.{safe_ext}"
        
        try:
            # Use b2_service which will handle content type during upload
            b2_service.upload_file(temp_file_path, b2_file_name, content_type)
            file_url = b2_service.get_file_url(b2_file_name)
            
            logger.info(f"Successfully uploaded {b2_file_name} (content_type: {content_type})")
            
            return {
                "file_url": file_url,
                "file_key": b2_file_name,
            }
        except Exception as e:
            logger.error(f"Failed to upload to B2: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to upload to B2: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to handle upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass


@router.post("/analyze")
async def analyze_screenshot(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    model: Optional[str] = Query("gemini-2.5-flash", description="Model to use: 'openai', 'gemini', 'gemini-2.5-flash', 'gemini-1.5-flash'")
):
    # 1. Save the uploaded file to a temporary local path for processing
    file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
    file_name = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save image: {str(e)}")

    # 2. Call AI Service with the local file path
    try:
        # Default to 'gemini-2.5-flash' if not specified or if 'gemini' is used as alias
        if model == "openai":
            scenario_result = openai_service.analyze_image(file_path)
        elif model == "gemini" or model == "gemini-2.5-flash":
            # Use gemini-2.5-flash as default Gemini model
            scenario_result = gemini_service.analyze_image(file_path)
        elif model == "gemini-1.5-flash":
            # Support legacy gemini-1.5-flash if explicitly requested
            temp_service = GeminiService(model_name="gemini-1.5-flash")
            scenario_result = temp_service.analyze_image(file_path)
        else:
            # Fallback to gemini-2.5-flash as default if model string is unknown
            scenario_result = gemini_service.analyze_image(file_path)

    except AIProcessingError as e:
        # Clean up file if AI fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        logger.error(f"Internal Server Error during analysis: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during analysis")

    # 3. Trigger Background Task for Persistence
    # The task will handle moving the file to B2 if configured
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
    with _records_lock:
        records = _load_records()
    return records[skip: skip + limit]

@router.delete("/records/{record_id}", response_model=AnalysisRecordInDB)
def delete_record(
    record_id: int
):
    """
    Delete an analysis record by ID.
    """
    with _records_lock:
        records = _load_records()
        record = next((r for r in records if int(r.get("id", -1)) == record_id), None)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        updated_records = [r for r in records if int(r.get("id", -1)) != record_id]
        _save_records(updated_records)
    
    # Optionally delete the file from disk as well
    # This part needs to be aware of B2 vs local
    # For now, we only attempt to delete if it looks like a local path
    image_path = str(record.get("image_path", ""))
    if image_path and not image_path.startswith('http'):
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                logger.warning(f"Could not delete file {image_path}")
            
    return record
