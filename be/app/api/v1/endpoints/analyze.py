import shutil
import os
import uuid
import logging
import json
import re
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from typing import List

from app.services.openai_service import OpenAIService
from app.schemas.analysis import AnalysisRecordInDB, AnalysisRecordCreate
from app.core.exceptions import AIProcessingError
from app.api import deps
from app.repositories.analysis_repository import AnalysisRepository

router = APIRouter()
openai_service = OpenAIService()
logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    Background task to save the analysis record to the database.
    """
    # We need a new DB session for the background task
    db = next(deps.get_db())
    try:
        repository = AnalysisRepository(db)
        cleaned_scenario_json = _extract_and_minify_json(scenario_result)
        if not cleaned_scenario_json:
            logger.error("Skipping save: could not extract valid JSON from model output.")
            return
        record_in = AnalysisRecordCreate(
            image_path=image_path,
            scenario_json=cleaned_scenario_json
        )
        repository.create(record_in)
        logger.info(f"Successfully saved analysis record for {image_path}")
    except Exception as e:
        logger.error(f"Failed to save analysis record in background: {e}")
    finally:
        db.close()

@router.post("/analyze")
async def analyze_screenshot(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    # 1. Save the uploaded file temporarily
    file_extension = file.filename.split(".")[-1] if file.filename else "jpg"
    file_name = f"{uuid.uuid4()}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save image: {str(e)}")

    # 2. Call OpenAI Service
    try:
        scenario_result = openai_service.analyze_image(file_path)
    except AIProcessingError as e:
        # Clean up file if AI fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="Internal Server Error during analysis")

    # 3. Trigger Background Task for Persistence
    background_tasks.add_task(save_analysis_record_task, file_path, scenario_result)

    # 4. Return the raw result as plain text
    return PlainTextResponse(content=scenario_result)

@router.get("/records", response_model=List[AnalysisRecordInDB])
def read_records(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(deps.get_db)
):
    """
    Retrieve all analysis records.
    """
    repository = AnalysisRepository(db)
    records = repository.get_multi(skip=skip, limit=limit)
    return records

@router.delete("/records/{record_id}", response_model=AnalysisRecordInDB)
def delete_record(
    record_id: int,
    db: Session = Depends(deps.get_db)
):
    """
    Delete an analysis record by ID.
    """
    repository = AnalysisRepository(db)
    record = repository.delete(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    # Optionally delete the file from disk as well
    if os.path.exists(record.image_path):
        try:
            os.remove(record.image_path)
        except OSError:
            logger.warning(f"Could not delete file {record.image_path}")
            
    return record
