import json
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, Response, UploadFile

from app.api.v1.http_helpers import correlation_response_headers, ensure_correlation_ids, json_compact
from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.core.log_context import bind_log_context, merge_with_log_context
from app.schemas.behavior_flow import BehaviorFlowOrganizeResponse
from app.schemas.state_graph import StateGraphOrganizeResponse
from app.services.behavior_flow_cluster_service import behavior_flow_cluster_service
from app.services.state_graph_pipeline_service import state_graph_pipeline_service

from .analyze_utils import safe_file_extension

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"
MULTI_IMG_SUB = "multi-img-input"
STATE_GRAPH_SUB = "state-graph-input"


async def _write_upload_capped(uf: UploadFile, dest_path: str, max_bytes: int) -> None:
    total = 0
    with open(dest_path, "wb") as buffer:
        while True:
            chunk = await uf.read(64 * 1024)
            if not chunk:
                break
            if total + len(chunk) > max_bytes:
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds max size of {max_bytes} bytes",
                ) from None
            buffer.write(chunk)
            total += len(chunk)


@router.post("/organize", response_model=BehaviorFlowOrganizeResponse)
async def organize_behavior_flows(
    response: Response,
    files: list[UploadFile] = File(
        ..., description="Unordered web UI screenshot images (multipart)"
    ),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_batch_id: Optional[str] = Header(default=None, alias="X-Batch-Id"),
) -> BehaviorFlowOrganizeResponse:
    """
    Accepts multiple unordered web UI images, groups them by behavior flow, and
    returns ordered `img_###` IDs per flow. Files are stored under
    `uploads/multi-img-input/<input_id>/` as `img_001.ext`, ...
    """
    max_n = settings.BEHAVIOR_FLOW_MAX_IMAGES
    max_b = settings.BEHAVIOR_FLOW_MAX_FILE_BYTES

    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if len(files) > max_n:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files: max {max_n} images per request",
        )

    input_id = str(uuid.uuid4())
    out_dir = os.path.join(UPLOAD_DIR, MULTI_IMG_SUB, input_id)
    os.makedirs(out_dir, exist_ok=True)

    id_path_pairs: list[tuple[str, str]] = []
    request_id, batch_id = ensure_correlation_ids(x_request_id, x_batch_id)
    # Convention: use headers like other endpoints; wire via Request if we need raw headers
    for idx, upload in enumerate(files, start=1):
        eid = f"img_{idx:03d}"
        ext = safe_file_extension(upload.filename, "png")
        # normalize double extension: img_001.png
        dest = os.path.join(out_dir, f"{eid}.{ext}")
        try:
            await _write_upload_capped(upload, dest, max_b)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to save upload %s", eid)
            raise HTTPException(status_code=500, detail=f"Could not save {eid}: {exc}") from exc
        id_path_pairs.append((eid, dest))

    with bind_log_context(
        request_id=request_id,
        batch_id=batch_id,
        input_id=input_id,
    ):
        logger.info(
            "behavior_flows organize started %s",
            json_compact(merge_with_log_context({"n_files": len(files), "input_id": input_id})),
        )
        try:
            result = await behavior_flow_cluster_service.organize(
                input_id=input_id,
                id_path_pairs=id_path_pairs,
            )
        except AIProcessingError as exc:
            logger.error("behavior_flows organize failed: %s", exc)
            raise HTTPException(
                status_code=502, detail=f"Model processing failed: {exc}"
            ) from exc
        except Exception as exc:
            logger.exception("behavior_flows organize internal error: %s", exc)
            raise HTTPException(
                status_code=500, detail="Internal error during behavior flow organization"
            ) from exc

    result_path = os.path.join(out_dir, "result.json")
    try:
        with open(result_path, "w", encoding="utf-8") as rf:
            rf.write(
                json.dumps(
                    result.model_dump(mode="json"),
                    ensure_ascii=False,
                    indent=2,
                )
            )
    except OSError as exc:
        logger.warning("Could not write result.json for %s: %s", input_id, exc)

    for h, v in correlation_response_headers(request_id, batch_id).items():
        response.headers[h] = v

    return result


@router.post("/state-graph", response_model=StateGraphOrganizeResponse)
async def build_state_graph_from_screenshots(
    response: Response,
    files: list[UploadFile] = File(
        ..., description="Unordered web UI screenshot images (multipart)"
    ),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_batch_id: Optional[str] = Header(default=None, alias="X-Batch-Id"),
) -> StateGraphOrganizeResponse:
    """
    Dedupe near-duplicate images, extract UI hierarchy (Gemini), infer user intents (GPT),
    then infer ordered flows with `image_id` content hashes as graph nodes.
    """
    max_n = settings.BEHAVIOR_FLOW_MAX_IMAGES
    max_b = settings.BEHAVIOR_FLOW_MAX_FILE_BYTES

    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if len(files) > max_n:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files: max {max_n} images per request",
        )

    input_id = str(uuid.uuid4())
    out_dir = os.path.join(UPLOAD_DIR, STATE_GRAPH_SUB, input_id)
    os.makedirs(out_dir, exist_ok=True)

    saved_paths: list[str] = []
    request_id, batch_id = ensure_correlation_ids(x_request_id, x_batch_id)

    for idx, upload in enumerate(files, start=1):
        eid = f"upload_{idx:03d}"
        ext = safe_file_extension(upload.filename, "png")
        dest = os.path.join(out_dir, f"{eid}.{ext}")
        try:
            await _write_upload_capped(upload, dest, max_b)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to save upload %s", eid)
            raise HTTPException(status_code=500, detail=f"Could not save {eid}: {exc}") from exc
        saved_paths.append(dest)

    with bind_log_context(
        request_id=request_id,
        batch_id=batch_id,
        input_id=input_id,
    ):
        logger.info(
            "behavior_flows state-graph started %s",
            json_compact(merge_with_log_context({"n_files": len(files), "input_id": input_id})),
        )
        try:
            result = await state_graph_pipeline_service.run(
                input_id=input_id,
                saved_paths=saved_paths,
                out_dir=out_dir,
            )
        except AIProcessingError as exc:
            logger.error("behavior_flows state-graph failed: %s", exc)
            raise HTTPException(
                status_code=502, detail=f"Model processing failed: {exc}"
            ) from exc
        except Exception as exc:
            logger.exception("behavior_flows state-graph internal error: %s", exc)
            raise HTTPException(
                status_code=500, detail="Internal error during state graph pipeline"
            ) from exc

    for h, v in correlation_response_headers(request_id, batch_id).items():
        response.headers[h] = v

    return result
