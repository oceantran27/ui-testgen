"""
Runs Router — API endpoints for run and image management.

POST /runs                  → Create a new run
GET  /runs                  → List all runs
GET  /runs/{run_id}         → Get run details
POST /runs/{run_id}/images  → Upload images to a run
GET  /runs/{run_id}/images  → List images of a run
POST /runs/{run_id}/submit  → Submit run for processing
POST /runs/{run_id}/cancel  → Cancel a run
GET  /runs/{run_id}/pipeline-log → Latest worker pipeline.log text (if any)
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.run import (
    RunCreateRequest,
    RunResponse,
    RunSubmitResponse,
    RunCancelResponse,
    RunListResponse,
    PipelineLogResponse,
)
from app.schemas.image import (
    UploadImagesResponse,
    ImageResponse,
    ImageListResponse,
)
from app.services import run_service, image_service
from app.services.pipeline_log_service import read_pipeline_log_incremental
from app.core.errors import RunNotFoundException
from app.constants.validation_artifacts import SCENARIO_VALIDATION_ARTIFACT_TYPES

router = APIRouter(prefix="/runs", tags=["Runs"])


# ──────────────────────────────────────────────
# Run CRUD
# ──────────────────────────────────────────────

@router.post("", response_model=RunResponse, status_code=201)
async def create_run(
    body: RunCreateRequest = RunCreateRequest(),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new processing run."""
    run = await run_service.create_run(
        db=db,
        project_name=body.project_name,
        description=body.description,
        config=body.config,
    )
    return RunResponse(
        run_id=run.id,
        project_name=run.project_name,
        description=run.description,
        status=run.status,
        total_images=run.total_images,
        config=run.config_json,
        created_at=run.created_at,
        updated_at=run.updated_at,
        current_phase=run.current_phase,
        current_node=run.current_node,
        progress_percentage=run.progress_percentage,
        graph_status=run.graph_status,
    )


@router.get("", response_model=RunListResponse)
async def list_runs(db: AsyncSession = Depends(get_db_session)):
    """List all runs."""
    runs = await run_service.list_runs(db)
    items = [
        RunResponse(
            run_id=r.id,
            project_name=r.project_name,
            description=r.description,
            status=r.status,
            total_images=r.total_images,
            valid_images=r.valid_images,
            invalid_images=r.invalid_images,
            config=r.config_json,
            created_at=r.created_at,
            updated_at=r.updated_at,
            submitted_at=r.submitted_at,
            started_at=r.started_at,
            completed_at=r.completed_at,
            error_message=r.error_message,
            current_phase=r.current_phase,
            current_node=r.current_node,
            progress_percentage=r.progress_percentage,
            graph_status=r.graph_status,
        )
        for r in runs
    ]
    return RunListResponse(runs=items, total=len(items))


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db_session)):
    """Get run details by ID."""
    run = await run_service.get_run(db, run_id)
    return RunResponse(
        run_id=run.id,
        project_name=run.project_name,
        description=run.description,
        status=run.status,
        total_images=run.total_images,
        valid_images=run.valid_images,
        invalid_images=run.invalid_images,
        config=run.config_json,
        created_at=run.created_at,
        updated_at=run.updated_at,
        submitted_at=run.submitted_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
        current_phase=run.current_phase,
        current_node=run.current_node,
        progress_percentage=run.progress_percentage,
        graph_status=run.graph_status,
    )


@router.get("/{run_id}/pipeline-log", response_model=PipelineLogResponse)
async def get_pipeline_log(
    run_id: str,
    from_byte: int = Query(0, ge=0, description="Byte offset for incremental tail reads (0 = full file)"),
    db: AsyncSession = Depends(get_db_session),
):
    """Return pipeline session log; use from_byte>0 after first response's next_byte for live tail."""
    await run_service.get_run(db, run_id)
    content, path, next_off, _ = read_pipeline_log_incremental(run_id, from_byte=from_byte)
    msg = None
    if content is None and path is None:
        msg = "No pipeline log directory found for this run (worker may not have started or logging is off)."
    elif content is None and path is not None:
        msg = "Session directory found but pipeline.log is missing or not readable yet."
    return PipelineLogResponse(
        run_id=run_id,
        content=content,
        path=path,
        message=msg,
        next_byte=next_off,
    )


# ──────────────────────────────────────────────
# Image upload & query
# ──────────────────────────────────────────────

@router.post("/{run_id}/images", response_model=UploadImagesResponse)
async def upload_images(
    run_id: str,
    files: List[UploadFile] = File(..., description="One or more UI screenshot files"),
    db: AsyncSession = Depends(get_db_session),
):
    """Upload one or more images to an existing run."""
    result = await image_service.upload_images(db, run_id, files)
    return UploadImagesResponse(**result)


@router.get("/{run_id}/images", response_model=ImageListResponse)
async def get_run_images(
    run_id: str,
    quality_status: Optional[str] = Query(default=None, description="Filter by quality_status"),
    db: AsyncSession = Depends(get_db_session),
):
    """List images for a run. Optional quality_status filter."""
    images = await image_service.get_run_images(db, run_id, quality_status=quality_status)
    items = [
        ImageResponse(
            image_id=img.id,
            original_filename=img.original_filename,
            format=img.format,
            file_size=img.file_size,
            width=img.width,
            height=img.height,
            upload_order=img.upload_order,
            storage_uri=img.storage_uri,
            quality_status=img.quality_status,
            sha256_hash=img.sha256_hash,
            created_at=img.created_at,
        )
        for img in images
    ]
    return ImageListResponse(run_id=run_id, total=len(items), images=items)




# ──────────────────────────────────────────────
# Run lifecycle actions
# ──────────────────────────────────────────────

@router.post("/{run_id}/submit", response_model=RunSubmitResponse)
async def submit_run(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Submit a run for background processing."""
    result = await run_service.submit_run(db, run_id)
    return RunSubmitResponse(**result)


@router.post("/{run_id}/cancel", response_model=RunCancelResponse)
async def cancel_run(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Cancel a run that has not started processing."""
    result = await run_service.cancel_run(db, run_id)
    return RunCancelResponse(**result)


@router.delete("/{run_id}", status_code=204)
async def delete_run(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Permanently delete a run and all associated data."""
    await run_service.delete_run(db, run_id)
    return None




@router.get("/{run_id}/images/{image_id}/thumbnail")
async def get_image_thumbnail(
    run_id: str,
    image_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Redirect to a presigned thumbnail URL for the given image."""
    from sqlalchemy import select
    from app.db.models.image import Image as ImageModel

    result = await db.execute(
        select(ImageModel)
        .where(ImageModel.id == image_id)
        .where(ImageModel.run_id == run_id)
    )
    img = result.scalar_one_or_none()
    if not img:
        raise HTTPException(status_code=404, detail={"error_code": "IMAGE_NOT_FOUND"})

    url = image_service.get_image_thumbnail_url(img)
    if not url:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "THUMBNAIL_NOT_FOUND", "message": "Thumbnail not yet generated."},
        )
    return RedirectResponse(url=url, status_code=302)


# ──────────────────────────────────────────────
# Phase 4 — Graph query endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/graph-status")
async def get_graph_status(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Get the current state of the LangGraph execution."""
    run = await run_service.get_run(db, run_id)
    return {
        "run_id": run.id,
        "graph_status": run.graph_status,
        "current_phase": run.current_phase,
        "current_node": run.current_node,
        "progress_percentage": run.progress_percentage,
        "graph_thread_id": run.graph_thread_id,
        "started_at": run.graph_started_at,
        "completed_at": run.graph_completed_at,
    }


@router.get("/{run_id}/graph-report")
async def get_graph_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the graph_execution_report.json."""
    artifact = await image_service.get_artifact_by_type(db, run_id, "graph_execution_report")
    if not artifact or not artifact.storage_uri:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "REPORT_NOT_FOUND", "message": f"No graph execution report found for run '{run_id}'."},
        )
    
    from app.services.storage_service import storage_service
    object_key = artifact.storage_uri.replace("s3://", "").split("/", 1)[-1]
    url = storage_service.get_presigned_url(object_key)
    return RedirectResponse(url=url, status_code=302)


@router.get("/{run_id}/artifacts")
async def get_artifacts(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all artifacts for a run."""
    from app.db.models.artifact import Artifact
    from sqlalchemy import select
    
    result = await db.execute(
        select(Artifact).where(Artifact.run_id == run_id)
    )
    artifacts = result.scalars().all()
    
    return {
        "run_id": run_id,
        "total": len(artifacts),
        "artifacts": [
            {
                "artifact_id": a.id,
                "type": a.artifact_type,
                "node_name": a.node_name,
                "storage_uri": a.storage_uri,
                "created_at": a.created_at,
            }
            for a in artifacts
        ]
    }


# ──────────────────────────────────────────────
# Phase 5 — Model call observability endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/model-calls")
async def list_model_calls(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all model calls for a run."""
    from app.db.models.model_call import ModelCall
    from sqlalchemy import select

    await run_service.get_run(db, run_id)  # raises RunNotFoundException if not found

    result = await db.execute(
        select(ModelCall).where(ModelCall.run_id == run_id).order_by(ModelCall.created_at)
    )
    calls = result.scalars().all()

    return {
        "run_id": run_id,
        "total": len(calls),
        "model_calls": [
            {
                "model_call_id": c.id,
                "node_name": c.node_name,
                "task_name": c.task_name,
                "provider": c.provider,
                "model_name": c.model_name,
                "request_type": c.request_type,
                "status": c.status,
                "latency_ms": c.latency_ms,
                "token_usage": {
                    "input_tokens": c.input_tokens,
                    "output_tokens": c.output_tokens,
                    "total_tokens": c.total_tokens,
                },
                "image_count": c.image_count,
                "retry_count": c.retry_count,
                "error_code": c.error_code,
                "created_at": c.created_at,
            }
            for c in calls
        ]
    }


@router.get("/{run_id}/model-calls/{call_id}")
async def get_model_call(
    run_id: str,
    call_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Get detail of a single model call."""
    from app.db.models.model_call import ModelCall
    from sqlalchemy import select
    from fastapi import HTTPException

    result = await db.execute(
        select(ModelCall)
        .where(ModelCall.id == call_id)
        .where(ModelCall.run_id == run_id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "MODEL_CALL_NOT_FOUND", "message": f"Model call '{call_id}' not found for run '{run_id}'."},
        )

    return {
        "model_call_id": call.id,
        "run_id": call.run_id,
        "job_id": call.job_id,
        "node_name": call.node_name,
        "task_name": call.task_name,
        "provider": call.provider,
        "model_name": call.model_name,
        "request_type": call.request_type,
        "status": call.status,
        "latency_ms": call.latency_ms,
        "token_usage": {
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "total_tokens": call.total_tokens,
        },
        "image_count": call.image_count,
        "retry_count": call.retry_count,
        "error_code": call.error_code,
        "error_message": call.error_message,
        "raw_output_artifact_id": call.raw_output_artifact_id,
        "created_at": call.created_at,
    }


@router.get("/{run_id}/model-config")
async def get_model_config(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the active model configuration snapshot for a run."""
    from app.core.config import settings

    await run_service.get_run(db, run_id)  # raises RunNotFoundException if not found

    return {
        "run_id": run_id,
        "default_model_provider": settings.DEFAULT_MODEL_PROVIDER,
        "gemini_text_model": settings.GEMINI_TEXT_MODEL,
        "gemini_vision_model": settings.GEMINI_VISION_MODEL,
        "openai_text_model": settings.OPENAI_TEXT_MODEL,
        "openai_vision_model": settings.OPENAI_VISION_MODEL,
        "pipeline_phase_models": {
            "joint_screen_understanding": {
                "provider": settings.JOINT_SCREEN_UNDERSTANDING_PROVIDER,
                "model": settings.JOINT_SCREEN_UNDERSTANDING_MODEL_NAME,
                "fallback_provider": settings.JOINT_SCREEN_UNDERSTANDING_FALLBACK_PROVIDER,
                "fallback_model": settings.JOINT_SCREEN_UNDERSTANDING_FALLBACK_MODEL_NAME,
            },
            "intent_aware_flow_discovery": {
                "provider": settings.FLOW_DISCOVERY_MODEL_PROVIDER,
                "model": settings.FLOW_DISCOVERY_MODEL_NAME,
                "fallback_model": settings.FLOW_DISCOVERY_FALLBACK_MODEL_NAME,
            },
            "behaviour_contract_builder": {
                "provider": settings.FLOW_DISCOVERY_MODEL_PROVIDER,
                "model": settings.FLOW_DISCOVERY_MODEL_NAME,
            },
            "bdd_scenario_generation": {
                "provider": settings.BDD_SCENARIO_GENERATION_MODEL_PROVIDER,
                "model": settings.BDD_SCENARIO_GENERATION_MODEL_NAME,
            },
            "scenario_evidence_audit": {
                "provider": settings.SCENARIO_VALIDATION_MODEL_PROVIDER,
                "model": settings.SCENARIO_VALIDATION_MODEL_NAME,
                "fallback_model": settings.SCENARIO_VALIDATION_FALLBACK_MODEL_NAME,
            },
        },
        "feature_flags": {
            "USE_LLM_FOR_BEHAVIOUR_CONTRACT_BUILDER": settings.USE_LLM_FOR_BEHAVIOUR_CONTRACT_BUILDER,
            "USE_LLM_FOR_SCENARIO_GENERATION": settings.USE_LLM_FOR_SCENARIO_GENERATION,
            "ENABLE_MODEL_FALLBACK": settings.ENABLE_MODEL_FALLBACK,
            "ENABLE_MODEL_RAW_RESPONSE_ARTIFACT": settings.ENABLE_MODEL_RAW_RESPONSE_ARTIFACT,
        },
        "retry_config": {
            "max_retries": settings.MODEL_MAX_RETRIES,
            "backoff_seconds": settings.MODEL_RETRY_BACKOFF_SECONDS,
            "text_timeout_seconds": settings.TEXT_MODEL_TIMEOUT_SECONDS,
            "vision_timeout_seconds": settings.VISION_MODEL_TIMEOUT_SECONDS,
        },
        "mock_mode": settings.MOCK_MODEL_MODE,
    }


# ──────────────────────────────────────────────
# Phase 6 — UI State Understanding endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/states")
async def list_ui_states(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all extracted UI states for a run."""
    from app.db.models.ui_state import UIState
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    await run_service.get_run(db, run_id)

    result = await db.execute(
        select(UIState)
        .options(selectinload(UIState.image))
        .where(UIState.run_id == run_id)
        .order_by(UIState.created_at)
    )
    states = result.scalars().unique().all()

    return {
        "run_id": run_id,
        "total": len(states),
        "states": [
            {
                "state_id": s.id,
                "image_id": s.image_id,
                "original_filename": (s.image.original_filename if s.image else None),
                "page_type": s.page_type,
                "screen_type": s.screen_type,
                "presentation_scope": s.presentation_scope,
                "outcome_state_type": s.outcome_state_type,
                "screen_purpose": s.screen_purpose,
                "domain": s.domain,
                "state_summary": s.state_summary,
                "state_signature": s.state_signature,
                "confidence": s.confidence,
                "confidence_label": s.confidence_label,
                "has_form": s.has_form,
                "has_table": s.has_table,
                "has_modal": s.has_modal,
                "has_feedback": s.has_feedback,
                "extraction_status": s.extraction_status,
                "created_at": s.created_at,
            }
            for s in states
        ]
    }


@router.get("/{run_id}/states/{state_id}")
async def get_ui_state(
    run_id: str,
    state_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Get a single UI state and all its elements."""
    from app.db.models.ui_state import UIState
    from app.db.models.ui_element import UIElement
    from sqlalchemy import select
    from fastapi import HTTPException

    # Get state
    result = await db.execute(
        select(UIState).where(UIState.id == state_id, UIState.run_id == run_id)
    )
    state = result.scalar_one_or_none()
    if not state:
        raise HTTPException(status_code=404, detail="UI State not found")

    # Get elements
    result = await db.execute(
        select(UIElement).where(UIElement.state_id == state_id).order_by(UIElement.created_at)
    )
    elements = result.scalars().all()

    raw_groups = state.interaction_groups_json
    if not isinstance(raw_groups, list):
        raw_groups = []

    element_to_group: dict[str, str] = {}
    interaction_groups: list[dict] = []
    for g in raw_groups:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("group_id") or "")
        merged_ids: list[str] = []
        for key in ("element_ids", "action_ids", "feedback_ids"):
            for x in g.get(key) or []:
                sid = str(x)
                merged_ids.append(sid)
                element_to_group[sid] = gid
        group_label = str(g.get("group_label") or "")
        group_type = str(g.get("group_type") or "")
        name = group_label or group_type or gid
        purpose = group_type or group_label or ""
        interaction_groups.append(
            {
                "group_id": gid
                if gid
                else f"ig_unknown_{len(interaction_groups)}",
                "group_name": name,
                "purpose": purpose,
                "element_ids": merged_ids,
                "group_type": group_type or None,
                "group_label": group_label or None,
            }
        )

    return {
        "state_id": state.id,
        "image_id": state.image_id,
        "page_type": state.page_type,
        "screen_type": state.screen_type,
        "presentation_scope": state.presentation_scope,
        "outcome_state_type": state.outcome_state_type,
        "screen_purpose": state.screen_purpose,
        "domain": state.domain,
        "state_summary": state.state_summary,
        "state_signature": state.state_signature,
        "confidence": state.confidence,
        "confidence_label": state.confidence_label,
        "has_form": state.has_form,
        "has_table": state.has_table,
        "has_modal": state.has_modal,
        "has_feedback": state.has_feedback,
        "extraction_status": state.extraction_status,
        "interaction_groups": interaction_groups,
        "ui_elements": [
            {
                "element_id": e.id,
                "type": e.type,
                "label": e.label,
                "text": e.text,
                "bbox": [e.bbox_ymin, e.bbox_xmin, e.bbox_ymax, e.bbox_xmax],
                "actionable": e.actionable,
                "is_feedback": e.is_feedback,
                "feedback_type": e.feedback_type,
                "action_type": e.action_type,
                "semantic_role": e.semantic_role,
                "visibility": e.visibility,
                "interaction_group_id": element_to_group.get(e.id),
            }
            for e in elements
        ],
        "feedback_elements": [],
        "primary_action_candidates": [],
    }


# ──────────────────────────────────────────────
# Agent 1 — UI State Extraction endpoints
# ──────────────────────────────────────────────


# Agent 3 — UI Flow Discovery endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/flows")
async def list_flows(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all discovered flows for a run."""
    from app.db.models.flow import Flow
    from sqlalchemy import select

    await run_service.get_run(db, run_id)

    result = await db.execute(
        select(Flow).where(Flow.run_id == run_id).order_by(Flow.created_at)
    )
    flows = result.scalars().all()

    def _id_list(blob) -> list:
        if not blob:
            return []
        if isinstance(blob, list):
            return blob
        if isinstance(blob, dict):
            return blob.get("ids") or blob.get("state_ids") or []
        return []

    def _flow_payload(f: Flow) -> dict:
        ordered = _id_list(f.ordered_state_ids_json)
        terminals = _id_list(f.terminal_state_ids_json)
        label = f.flow_label or f.name or f.id
        return {
            "flow_id": f.id,
            "name": f.name,
            "flow_label": label,
            "flow_type": f.flow_type,
            "input_level": f.input_level,
            "start_state_id": f.start_state_id,
            "entry_state_id": f.entry_state_id or f.start_state_id,
            "ordered_state_ids": ordered,
            "state_ids": ordered,
            "terminal_state_ids": terminals,
            "state_sequence": f.state_sequence_json.get("sequence", []),
            "flow_completeness": f.flow_completeness_json,
            "intent_readiness": f.intent_readiness_json,
            "flow_evidence_package": f.flow_evidence_package_json,
            "confidence": f.confidence,
            "confidence_label": f.confidence_label,
            "created_at": f.created_at,
        }

    return {
        "run_id": run_id,
        "total": len(flows),
        "flows": [_flow_payload(f) for f in flows],
    }


@router.get("/{run_id}/flows/{flow_id}")
async def get_flow_detail(
    run_id: str,
    flow_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Get detailed information about a specific flow and its transitions."""
    from app.db.models.flow import Flow
    from app.db.models.flow_transition import FlowTransition
    from sqlalchemy import select
    from fastapi import HTTPException

    # Get flow
    result = await db.execute(
        select(Flow).where(Flow.id == flow_id, Flow.run_id == run_id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    # Get transitions
    result = await db.execute(
        select(FlowTransition).where(FlowTransition.flow_id == flow_id).order_by(FlowTransition.created_at)
    )
    transitions = result.scalars().all()

    ordered = (
        flow.ordered_state_ids_json.get("ids", [])
        if isinstance(flow.ordered_state_ids_json, dict)
        else (flow.ordered_state_ids_json if isinstance(flow.ordered_state_ids_json, list) else [])
    )
    terminals_raw = flow.terminal_state_ids_json or {}
    terminals = (
        terminals_raw.get("ids", [])
        if isinstance(terminals_raw, dict)
        else (terminals_raw if isinstance(terminals_raw, list) else [])
    )
    flow_label = flow.flow_label or flow.name or flow.id

    return {
        "flow_id": flow.id,
        "name": flow.name,
        "flow_label": flow_label,
        "flow_type": flow.flow_type,
        "input_level": flow.input_level,
        "start_state_id": flow.start_state_id,
        "entry_state_id": flow.entry_state_id or flow.start_state_id,
        "ordered_state_ids": ordered,
        "state_ids": ordered,
        "terminal_state_ids": terminals,
        "paths": flow.paths_json,
        "confidence": flow.confidence,
        "confidence_label": flow.confidence_label,
        "warnings": flow.warnings_json,
        "transitions": [
            {
                "transition_id": t.id,
                "from_state_id": t.from_state_id,
                "to_state_id": t.to_state_id,
                "transition_type": t.transition_type,
                "trigger": t.trigger_json,
                "target_state_evidence": t.target_state_evidence_json,
                "transition_basis": (t.transition_basis or "").split(",") if t.transition_basis else [],
                "ordering_strength": t.ordering_strength,
                "transition_certainty": t.transition_certainty,
                "uncertainty_reason": t.uncertainty_reason,
                "score": t.score,
                "confidence_label": t.confidence_label,
                "reason": t.reason,
            }
            for t in transitions
        ]
    }


@router.get("/{run_id}/flow-discovery-report")
async def get_flow_discovery_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the full flow discovery report from artifacts."""
    from app.db.models.artifact import Artifact
    from app.services.storage_service import storage_service
    from sqlalchemy import select
    import json

    result = await db.execute(
        select(Artifact).where(
            Artifact.run_id == run_id, 
            Artifact.artifact_type == "flow_discovery_report"
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        return {"error": "Report not found"}

    content = storage_service.download_file(artifact.storage_uri)
    return json.loads(content)


# ──────────────────────────────────────────────
# Agent 2 — Semantic Canonicalization endpoints
# ──────────────────────────────────────────────

# Agent 5 — Behaviour Intent Inference endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/behaviour-intents")
async def list_behaviour_intents(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all inferred behaviour intents for a run."""
    from app.db.models.behaviour_intent import BehaviourIntent
    from sqlalchemy import select

    result = await db.execute(
        select(BehaviourIntent).where(BehaviourIntent.run_id == run_id).order_by(BehaviourIntent.created_at)
    )
    intents = result.scalars().all()

    return {
        "run_id": run_id,
        "total": len(intents),
        "intents": [
            {
                "intent_id": i.id,
                "flow_id": i.flow_id,
                "behaviour_name": i.behaviour_name,
                "intent_type": i.intent_type,
                "test_path": i.test_path,
                "user_intent": i.user_intent,
                "business_goal": i.business_goal,
                "start_state": i.start_state,
                "end_state": i.end_state,
                "confidence": i.confidence,
                "created_at": i.created_at,
            }
            for i in intents
        ]
    }


@router.get("/{run_id}/behaviour-intent-report")
async def get_behaviour_intent_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the full behaviour intent report from artifacts."""
    from app.db.models.artifact import Artifact
    from app.services.storage_service import storage_service
    from sqlalchemy import select
    import json

    result = await db.execute(
        select(Artifact).where(
            Artifact.run_id == run_id, 
            Artifact.artifact_type == "behaviour_intent_report"
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        return {"error": "Report not found"}

    content = storage_service.download_file(artifact.storage_uri)
    return json.loads(content)


# Agent 6 — BDD Scenario Generation endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/scenarios")
async def list_behaviour_scenarios(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all draft behaviour scenarios for a run."""
    from app.db.models.behaviour_scenario import BehaviourScenario
    from sqlalchemy import select

    result = await db.execute(
        select(BehaviourScenario).where(BehaviourScenario.run_id == run_id).order_by(BehaviourScenario.created_at)
    )
    scenarios = result.scalars().all()

    return {
        "run_id": run_id,
        "total": len(scenarios),
        "scenarios": [
            {
                "scenario_id": s.id,
                "intent_id": s.intent_id,
                "title": s.scenario_title,
                "type": s.scenario_type,
                "scenario_type": s.scenario_type,
                "grounding_mode": s.grounding_mode,
                "confidence": s.initial_confidence,
                "status": s.status,
                "validation_status": s.validation_status,
            }
            for s in scenarios
        ]
    }


@router.get("/{run_id}/scenarios/{scenario_id}")
async def get_behaviour_scenario_detail(
    run_id: str,
    scenario_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Get full detail of a specific behaviour scenario."""
    from app.db.models.behaviour_scenario import BehaviourScenario
    from sqlalchemy import select

    result = await db.execute(
        select(BehaviourScenario).where(
            BehaviourScenario.id == scenario_id,
            BehaviourScenario.run_id == run_id
        )
    )
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return {
        "scenario_id": scenario.id,
        "run_id": scenario.run_id,
        "intent_id": scenario.intent_id,
        "flow_id": scenario.flow_id,
        "feature": scenario.feature,
        "scenario_title": scenario.scenario_title,
        "scenario_type": scenario.scenario_type,
        "gherkin_text": scenario.gherkin_text,
        "bdd_steps": (
            (scenario.bdd_steps_json.get("steps") or scenario.bdd_steps_json.get("bdd_steps", []))
            if isinstance(scenario.bdd_steps_json, dict)
            else []
        ),
        "status": scenario.status,
        "validation": {
            "validation_status": scenario.validation_status,
            "final_reliability": scenario.final_reliability,
            "hallucination_flags": scenario.hallucination_flags_json,
            "acceptance_decision": scenario.acceptance_decision_json,
            "scores": scenario.scores_json,
            "validated_at": scenario.validated_at,
        }
    }


@router.get("/{run_id}/scenario-validation-report")
async def get_scenario_validation_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the full scenario grounding validation report from artifacts."""
    from app.db.models.artifact import Artifact
    from app.services.storage_service import storage_service
    from sqlalchemy import select
    import json

    result = await db.execute(
        select(Artifact).where(
            Artifact.run_id == run_id, 
            Artifact.artifact_type == "scenario_grounding_validation_report"
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        return {"error": "Report not found"}

    content = storage_service.download_file(artifact.storage_uri)
    return json.loads(content)


# ──────────────────────────────────────────────
# Agent 7 — Scenario Validation & Final Output
# ──────────────────────────────────────────────

@router.get("/{run_id}/scenario-validation")
async def get_scenario_validation(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return Agent 7 scenario validation package (artifact: scenario_evidence_audit_report or legacy)."""

    await run_service.get_run(db, run_id)

    from app.services.validation_report_loader import load_latest_scenario_validation_payload

    payload = await load_latest_scenario_validation_payload(db, run_id)
    if not payload:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "SCENARIO_VALIDATION_REPORT_NOT_FOUND",
                "message": (
                    f"No scenario validation artifact for run '{run_id}' "
                    f"(expected {', '.join(SCENARIO_VALIDATION_ARTIFACT_TYPES)})."
                ),
            },
        )
    return payload


@router.get("/{run_id}/research-output")
async def get_research_output(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return validated scenario package JSON (legacy URL name; same payload as GET /scenario-validation)."""

    await run_service.get_run(db, run_id)

    from app.services.validation_report_loader import load_latest_scenario_validation_payload

    payload = await load_latest_scenario_validation_payload(db, run_id)
    if not payload:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "RESEARCH_OUTPUT_NOT_FOUND",
                "message": f"No scenario validation artifact for run '{run_id}'.",
            },
        )
    return payload

