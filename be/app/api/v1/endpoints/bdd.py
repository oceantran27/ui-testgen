import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Response, UploadFile

from app.core.exceptions import AIProcessingError
from app.core.log_context import bind_log_context, merge_with_log_context
from app.core.model_selection import normalize_analysis_model_name
from app.schemas.bdd_happy_path import BddHappyPathResult
from app.services.bdd_happy_path_service import bdd_happy_path_service

from .analyze_utils import safe_remove_local_file, save_analysis_record_task, save_upload_file

router = APIRouter()
logger = logging.getLogger(__name__)


def _json_compact(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _sanitize_id(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalized = str(raw).strip()
    if not normalized:
        return None
    if len(normalized) > 128:
        return normalized[:128]
    return normalized


def _build_request_context(
    *,
    request_id: str | None = None,
    batch_id: str | None = None,
) -> dict[str, str]:
    return {
        "request_id": _sanitize_id(request_id) or str(uuid.uuid4()),
        "batch_id": _sanitize_id(batch_id) or str(uuid.uuid4()),
        "model_name": normalize_analysis_model_name("gemini-2.5-flash"),
        "analysis_source": "bdd_happy_path_file_upload",
    }


def _response_headers(ctx: dict[str, str]) -> dict[str, str]:
    return {
        "X-Request-Id": ctx["request_id"],
        "X-Batch-Id": ctx["batch_id"],
        "Access-Control-Expose-Headers": "X-Request-Id,X-Batch-Id",
    }


@router.post("/happy-path", response_model=BddHappyPathResult)
async def bdd_happy_path_from_image(
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_batch_id: Optional[str] = Header(default=None, alias="X-Batch-Id"),
):
    file_path = save_upload_file(file)
    request_context = _build_request_context(
        request_id=x_request_id,
        batch_id=x_batch_id,
    )

    with bind_log_context(**request_context):
        logger.info(
            "BDD happy path: started %s",
            _json_compact(
                merge_with_log_context(
                    {
                        "event": "bdd_happy_path_started",
                        "filename": file.filename,
                    }
                )
            ),
        )
        try:
            result = await bdd_happy_path_service.generate(file_path)
        except AIProcessingError as exc:
            safe_remove_local_file(file_path)
            logger.error("BDD happy path failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            safe_remove_local_file(file_path)
            logger.error("BDD happy path internal error: %s", exc)
            raise HTTPException(
                status_code=500, detail="Internal server error during BDD generation"
            ) from exc

        serialized = _json_compact(result.model_dump(mode="json"))
        background_tasks.add_task(save_analysis_record_task, file_path, serialized)
        logger.info(
            "BDD happy path: completed %s",
            _json_compact(
                merge_with_log_context(
                    {
                        "event": "bdd_happy_path_completed",
                        "scenario_count": len(result.scenarios),
                    }
                )
            ),
        )
        for header_name, header_value in _response_headers(request_context).items():
            response.headers[header_name] = header_value
        return result
