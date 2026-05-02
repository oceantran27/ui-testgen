import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Response, UploadFile

from app.api.v1.http_helpers import correlation_response_headers, ensure_correlation_ids, json_compact
from app.core.exceptions import AIProcessingError
from app.core.log_context import bind_log_context, merge_with_log_context
from app.core.model_selection import normalize_analysis_model_name
from app.schemas.bdd_happy_path import BddHappyPathResult
from app.schemas.bdd_happy_path_ranked import BddHappyPathRankedResponse
from app.services.bdd_happy_path_service import bdd_happy_path_service
from app.services.bdd_two_stage_service import bdd_two_stage_service
from app.services.bdd_with_ranking_service import bdd_with_ranking_service

from .analyze_utils import safe_remove_local_file, save_analysis_record_task, save_upload_file

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_request_context(
    *,
    request_id: str | None = None,
    batch_id: str | None = None,
    analysis_source: str = "bdd_happy_path_file_upload",
) -> dict[str, str]:
    rid, bid = ensure_correlation_ids(request_id, batch_id)
    return {
        "request_id": rid,
        "batch_id": bid,
        "model_name": normalize_analysis_model_name("gemini-2.5-flash"),
        "analysis_source": analysis_source,
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
            json_compact(
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

        serialized = json_compact(result.model_dump(mode="json"))
        background_tasks.add_task(save_analysis_record_task, file_path, serialized)
        logger.info(
            "BDD happy path: completed %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "bdd_happy_path_completed",
                        "scenario_count": len(result.scenarios),
                    }
                )
            ),
        )
        for header_name, header_value in correlation_response_headers(
            request_context["request_id"], request_context["batch_id"]
        ).items():
            response.headers[header_name] = header_value
        return result


@router.post("/happy-path-bridged", response_model=BddHappyPathResult)
async def bdd_happy_path_bridged_from_image(
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_batch_id: Optional[str] = Header(default=None, alias="X-Batch-Id"),
):
    """Two-agent pipeline: vision bridge JSON, then text-only BDD (same response shape as /happy-path)."""
    file_path = save_upload_file(file)
    request_context = _build_request_context(
        request_id=x_request_id,
        batch_id=x_batch_id,
        analysis_source="bdd_happy_path_two_stage_file_upload",
    )

    with bind_log_context(**request_context):
        logger.info(
            "BDD happy path bridged: started %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "bdd_happy_path_bridged_started",
                        "filename": file.filename,
                    }
                )
            ),
        )
        try:
            result = await bdd_two_stage_service.generate(file_path)
        except AIProcessingError as exc:
            safe_remove_local_file(file_path)
            logger.error("BDD happy path bridged failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            safe_remove_local_file(file_path)
            logger.error("BDD happy path bridged internal error: %s", exc)
            raise HTTPException(
                status_code=500, detail="Internal server error during BDD bridged generation"
            ) from exc

        serialized = json_compact(result.model_dump(mode="json"))
        background_tasks.add_task(save_analysis_record_task, file_path, serialized)
        logger.info(
            "BDD happy path bridged: completed %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "bdd_happy_path_bridged_completed",
                        "scenario_count": len(result.scenarios),
                    }
                )
            ),
        )
        for header_name, header_value in correlation_response_headers(
            request_context["request_id"], request_context["batch_id"]
        ).items():
            response.headers[header_name] = header_value
        return result


@router.post("/happy-path-ranked", response_model=BddHappyPathRankedResponse)
async def bdd_happy_path_ranked_from_image(
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_batch_id: Optional[str] = Header(default=None, alias="X-Batch-Id"),
):
    """
    Returns BDD with scenarios reordered by a second LLM pass using `feature.business_intent`.
    `vision` is a placeholder for API shape compatibility.
    """
    file_path = save_upload_file(file)
    request_context = _build_request_context(
        request_id=x_request_id,
        batch_id=x_batch_id,
    )

    with bind_log_context(**request_context):
        logger.info(
            "BDD happy path ranked: started %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "bdd_happy_path_ranked_started",
                        "filename": file.filename,
                    }
                )
            ),
        )
        try:
            result = await bdd_with_ranking_service.generate_ranked_response(file_path)
        except AIProcessingError as exc:
            safe_remove_local_file(file_path)
            logger.error("BDD happy path ranked failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            safe_remove_local_file(file_path)
            logger.error("BDD happy path ranked internal error: %s", exc)
            raise HTTPException(
                status_code=500, detail="Internal server error during BDD ranked generation"
            ) from exc

        serialized = json_compact(result.model_dump(mode="json"))
        background_tasks.add_task(save_analysis_record_task, file_path, serialized)
        logger.info(
            "BDD happy path ranked: completed %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "bdd_happy_path_ranked_completed",
                        "scenario_count": len(result.bdd.scenarios),
                    }
                )
            ),
        )
        for header_name, header_value in correlation_response_headers(
            request_context["request_id"], request_context["batch_id"]
        ).items():
            response.headers[header_name] = header_value
        return result
