import shutil
import os
import uuid
import logging
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

def _clean_json_string(s: str) -> str:
    """Removes markdown-style code fences from a string."""
    s = s.strip()
    if s.startswith("```json"):
        s = s[len("```json"):].strip()
    if s.endswith("```"):
        s = s[:-len("```")].strip()
    return s

def save_analysis_record_task(image_path: str, scenario_result: str):
    """
    Background task to save the analysis record to the database.
    """
    # We need a new DB session for the background task
    db = next(deps.get_db())
    try:
        repository = AnalysisRepository(db)
        
        cleaned_scenario_json = _clean_json_string(scenario_result)
        
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
