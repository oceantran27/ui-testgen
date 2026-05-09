import json
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

from app.api.v1.http_helpers import correlation_response_headers, ensure_correlation_ids, json_compact
from app.api.v1.upload_file_utils import safe_file_extension
from app.core.config import settings
from app.core.log_context import bind_log_context, merge_with_log_context
from app.langgraph.graph import builder
from app.schemas.state_graph import StateGraphStartResponse

# Setup Checkpointer
conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(conn)
pipeline_graph = builder.compile(checkpointer=memory)

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"
STATE_GRAPH_SUB = "state-graph-input"


def _parse_state_graph_input_id(raw_id: str) -> str:
    try:
        return str(uuid.UUID(raw_id.strip()))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid input_id (expected UUID)") from None


async def _run_state_graph_job(input_id: str, saved_paths: list[str], out_dir: str) -> None:
    try:
        thread = {"configurable": {"thread_id": input_id}}
        await pipeline_graph.ainvoke(
            {
                "input_id": input_id,
                "saved_paths": saved_paths,
                "out_dir": out_dir,
                "extract_model": settings.STATE_GRAPH_UI_EXTRACTION_MODEL,
                "intent_model": settings.STATE_GRAPH_USER_INTENT_MODEL,
                "flow_model": settings.STATE_GRAPH_FLOW_MODEL,
                "e2e_model": settings.STATE_GRAPH_E2E_SCENARIO_MODEL,
            },
            thread,
        )
    except Exception as exc:
        logger.error(
            "state graph job finished with error (%s): %s",
            input_id,
            exc,
            exc_info=True,
        )


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


@router.post("/state-graph", response_model=StateGraphStartResponse)
async def build_state_graph_from_screenshots(
    response: Response,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(
        ..., description="Unordered web UI screenshot images (multipart)"
    ),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    x_batch_id: Optional[str] = Header(default=None, alias="X-Batch-Id"),
) -> StateGraphStartResponse:
    """
    Accept screenshots, persist them, then run the full pipeline asynchronously.
    Stream progress via GET .../behavior-flows/state-graph/status/{input_id}.
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
            "behavior_flows state-graph queued %s",
            json_compact(merge_with_log_context({"n_files": len(files), "input_id": input_id})),
        )
        background_tasks.add_task(_run_state_graph_job, input_id, saved_paths, out_dir)

    for h, v in correlation_response_headers(request_id, batch_id).items():
        response.headers[h] = v

    return StateGraphStartResponse(input_id=input_id, status="running")


@router.get("/state-graph/status/{input_id}")
async def state_graph_job_status(input_id: str):
    """SSE streaming endpoint for asynchronous state-graph pipeline progress and outcome."""

    input_id_clean = _parse_state_graph_input_id(input_id)
    thread = {"configurable": {"thread_id": input_id_clean}}

    async def event_generator():
        try:
            async for event in pipeline_graph.astream(None, thread, stream_mode="updates"):
                for node, state_update in event.items():
                    data = {
                        "status": "running",
                        "current_phase": node,
                        "data": state_update,
                    }
                    yield f"data: {json.dumps(data, default=str)}\n\n"

            final_state = pipeline_graph.get_state(thread)
            if final_state and final_state.values:
                error = final_state.values.get("error")
                if error:
                    yield f"data: {json.dumps({'status': 'failed', 'error': error})}\n\n"
                else:
                    yield f"data: {json.dumps({'status': 'completed', 'result': 'Available in final_test_output.json'})}\n\n"
        except Exception as e:
            logger.error("Stream error for %s: %s", input_id_clean, e)
            yield f"data: {json.dumps({'status': 'failed', 'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
