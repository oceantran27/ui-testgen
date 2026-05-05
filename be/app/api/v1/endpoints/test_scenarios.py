import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Response, UploadFile

from app.api.v1.http_helpers import correlation_response_headers, ensure_correlation_ids, json_compact
from app.core.exceptions import AIProcessingError
from app.core.log_context import bind_log_context, merge_with_log_context
from app.core.model_selection import normalize_analysis_model_name
from app.schemas.test_scenario_generation import TestScenarioSuite
from app.services.single_stage_test_scenario_service import single_stage_test_scenario_service
from app.services.two_stage_test_scenario_service import two_stage_test_scenario_service

from .analyze_utils import safe_remove_local_file, save_analysis_record_task, save_upload_file

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_request_context(
    *,
    request_id: str | None = None,
    batch_id: str | None = None,
    analysis_source: str = "test_scenario_single_stage_file_upload",
) -> dict[str, str]:
    rid, bid = ensure_correlation_ids(request_id, batch_id)
    return {
        "request_id": rid,
        "batch_id": bid,
        "model_name": normalize_analysis_model_name("gemini-2.5-flash"),
        "analysis_source": analysis_source,
    }


@router.post("/from-image", response_model=TestScenarioSuite)
async def generate_test_scenarios_from_image(
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
            "Single-stage test scenarios: started %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "test_scenario_single_stage_started",
                        "filename": file.filename,
                    }
                )
            ),
        )
        try:
            result = await single_stage_test_scenario_service.generate(file_path)
        except AIProcessingError as exc:
            safe_remove_local_file(file_path)
            logger.error("Single-stage test scenario generation failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            safe_remove_local_file(file_path)
            logger.error("Single-stage test scenario internal error: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="Internal server error during test scenario generation",
            ) from exc

        serialized = json_compact(result.model_dump(mode="json"))
        background_tasks.add_task(save_analysis_record_task, file_path, serialized)
        logger.info(
            "Single-stage test scenarios: completed %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "test_scenario_single_stage_completed",
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


@router.post("/from-image-bridged", response_model=TestScenarioSuite)
async def generate_test_scenarios_from_image_bridged(
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_batch_id: Optional[str] = Header(default=None, alias="X-Batch-Id"),
):
    """Two-stage pipeline: UI hierarchy (vision), then text-only scenario suite (same response shape as /from-image)."""
    file_path = save_upload_file(file)
    request_context = _build_request_context(
        request_id=x_request_id,
        batch_id=x_batch_id,
        analysis_source="test_scenario_two_stage_file_upload",
    )

    with bind_log_context(**request_context):
        logger.info(
            "Two-stage test scenarios: started %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "test_scenario_two_stage_started",
                        "filename": file.filename,
                    }
                )
            ),
        )
        try:
            result = await two_stage_test_scenario_service.generate(file_path)
        except AIProcessingError as exc:
            safe_remove_local_file(file_path)
            logger.error("Two-stage test scenario generation failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            safe_remove_local_file(file_path)
            logger.error("Two-stage test scenario internal error: %s", exc)
            raise HTTPException(
                status_code=500,
                detail="Internal server error during bridged test scenario generation",
            ) from exc

        serialized = json_compact(result.model_dump(mode="json"))
        background_tasks.add_task(save_analysis_record_task, file_path, serialized)
        logger.info(
            "Two-stage test scenarios: completed %s",
            json_compact(
                merge_with_log_context(
                    {
                        "event": "test_scenario_two_stage_completed",
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
