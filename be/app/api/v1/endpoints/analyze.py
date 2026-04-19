import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.exceptions import AIProcessingError
from app.schemas.analysis import AnalyzeResponse
from app.services.llm_provider import LLMProviderFactory
from app.services.multi_agent_pipeline_service import MultiAgentPipelineService

router = APIRouter()
logger = logging.getLogger(__name__)

def _save_upload_file(file: UploadFile) -> str:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "screenshot.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(dir=uploads_dir, suffix=suffix, delete=False) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        return temp_file.name


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_screenshot(file: UploadFile = File(...)):
    if not (file.content_type or "").lower().startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported.")

    file_path = _save_upload_file(file)

    try:
        provider = LLMProviderFactory.create_from_settings()
        pipeline = MultiAgentPipelineService(provider=provider)
        result = pipeline.run(file_path)
        return AnalyzeResponse.model_validate(result)
    except AIProcessingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected backend failure during screenshot analysis")
        raise HTTPException(status_code=500, detail="Internal Server Error during analysis") from exc
    finally:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Could not remove temporary upload file: %s", file_path)
