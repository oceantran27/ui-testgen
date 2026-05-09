"""
Runs Router — API endpoints for run and image management.

POST /runs                  → Create a new run
GET  /runs                  → List all runs
GET  /runs/{run_id}         → Get run details
POST /runs/{run_id}/images  → Upload images to a run
GET  /runs/{run_id}/images  → List images of a run
POST /runs/{run_id}/submit  → Submit run for processing
POST /runs/{run_id}/cancel  → Cancel a run
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
)
from app.schemas.image import (
    UploadImagesResponse,
    ImageResponse,
    ImageListResponse,
)
from app.services import run_service, image_service
from app.core.errors import RunNotFoundException

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
            canonical_images=r.canonical_images,
            duplicate_groups_count=r.duplicate_groups_count,
            config=r.config_json,
            created_at=r.created_at,
            updated_at=r.updated_at,
            submitted_at=r.submitted_at,
            started_at=r.started_at,
            completed_at=r.completed_at,
            error_message=r.error_message,
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
        canonical_images=run.canonical_images,
        duplicate_groups_count=run.duplicate_groups_count,
        config=run.config_json,
        created_at=run.created_at,
        updated_at=run.updated_at,
        submitted_at=run.submitted_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_message=run.error_message,
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
    is_canonical: Optional[bool] = Query(default=None, description="Filter by is_canonical"),
    db: AsyncSession = Depends(get_db_session),
):
    """List images for a run. Optional quality_status and is_canonical filters."""
    images = await image_service.get_run_images(db, run_id, quality_status=quality_status, is_canonical=is_canonical)
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
            duplicate_status=img.duplicate_status,
            duplicate_group_id=img.duplicate_group_id,
            is_canonical=img.is_canonical,
            duplicate_type=img.duplicate_type,
            phash=img.phash,
            dhash=img.dhash,
            created_at=img.created_at,
        )
        for img in images
    ]
    return ImageListResponse(run_id=run_id, total=len(items), images=items)


@router.get("/{run_id}/duplicate-report")
async def get_duplicate_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the duplicate_detection_report.json for a completed run."""
    artifact = await image_service.get_artifact_by_type(db, run_id, "duplicate_detection_report")
    if not artifact or not artifact.storage_uri:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "REPORT_NOT_FOUND", "message": f"No duplicate report found for run '{run_id}'."},
        )
    
    # In a real app, we might want to parse and return JSON, but here we redirect to storage for consistency with Phase 2
    from app.services.storage_service import storage_service
    object_key = artifact.storage_uri.replace("s3://", "").split("/", 1)[-1]
    url = storage_service.get_presigned_url(object_key)
    return RedirectResponse(url=url, status_code=302)


@router.get("/{run_id}/duplicate-groups")
async def get_duplicate_groups(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all duplicate groups for a run."""
    from app.db.models.duplicate_group import DuplicateGroup
    from sqlalchemy import select
    
    result = await db.execute(
        select(DuplicateGroup).where(DuplicateGroup.run_id == run_id)
    )
    groups = result.scalars().all()
    
    return {
        "run_id": run_id,
        "total": len(groups),
        "groups": [
            {
                "group_id": g.id,
                "canonical_image_id": g.canonical_image_id,
                "type": g.duplicate_type,
                "confidence": g.confidence,
                "reason": g.group_reason
            }
            for g in groups
        ]
    }


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


# ──────────────────────────────────────────────
# Phase 2 — Preprocessing query endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/preprocessing-report")
async def get_preprocessing_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the image_quality_report.json for a completed preprocessing phase."""
    report = await image_service.get_preprocessing_report(db, run_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "REPORT_NOT_FOUND", "message": f"No preprocessing report found for run '{run_id}'."},
        )
    return report


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
        "feature_flags": {
            "USE_VLM_FOR_QUALITY_CHECK": settings.USE_VLM_FOR_QUALITY_CHECK,
            "USE_VLM_FOR_DUPLICATE_CHECK": settings.USE_VLM_FOR_DUPLICATE_CHECK,
            "USE_VLM_FOR_UI_STATE_EXTRACTION": settings.USE_VLM_FOR_UI_STATE_EXTRACTION,
            "USE_LLM_FOR_FLOW_DISCOVERY": settings.USE_LLM_FOR_FLOW_DISCOVERY,
            "USE_LLM_FOR_SCENARIO_GENERATION": settings.USE_LLM_FOR_SCENARIO_GENERATION,
            "USE_LLM_FOR_SCENARIO_VALIDATION": settings.USE_LLM_FOR_SCENARIO_VALIDATION,
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

    await run_service.get_run(db, run_id)

    result = await db.execute(
        select(UIState).where(UIState.run_id == run_id).order_by(UIState.created_at)
    )
    states = result.scalars().all()

    return {
        "run_id": run_id,
        "total": len(states),
        "states": [
            {
                "state_id": s.id,
                "image_id": s.image_id,
                "page_type": s.page_type,
                "state_summary": s.state_summary,
                "state_signature": s.state_signature,
                "confidence": s.confidence,
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

    return {
        "state_id": state.id,
        "image_id": state.image_id,
        "page_type": state.page_type,
        "state_summary": state.state_summary,
        "state_signature": state.state_signature,
        "confidence": state.confidence,
        "has_form": state.has_form,
        "has_table": state.has_table,
        "has_modal": state.has_modal,
        "has_feedback": state.has_feedback,
        "extraction_status": state.extraction_status,
        "ui_elements": [
            {
                "element_id": e.id,
                "type": e.type,
                "label": e.label,
                "text": e.text,
                "placeholder": e.placeholder,
                "bbox": {
                    "x_min": e.bbox_xmin,
                    "y_min": e.bbox_ymin,
                    "x_max": e.bbox_xmax,
                    "y_max": e.bbox_ymax,
                },
                "actionable": e.actionable,
                "action_type": e.action_type,
                "is_feedback": e.is_feedback,
                "feedback_type": e.feedback_type,
                "confidence": e.confidence,
            }
            for e in elements
        ]
    }


# ──────────────────────────────────────────────
# Phase 7 — Input Level Detection endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/input-level")
async def get_input_level(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the detected input level and related metadata."""
    from app.services.run_service import run_service
    run = await run_service.get_run(db, run_id)

    return {
        "run_id": run_id,
        "input_level": run.input_level,
        "input_level_confidence": run.input_level_confidence,
        "input_level_reason": run.input_level_reason,
    }


@router.get("/{run_id}/input-level-report")
async def get_input_level_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the full input level detection report from artifacts."""
    from app.db.models.artifact import Artifact
    from app.services.storage_service import storage_service
    from sqlalchemy import select
    import json

    result = await db.execute(
        select(Artifact).where(
            Artifact.run_id == run_id, 
            Artifact.artifact_type == "input_level_detection_report"
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        return {"error": "Report not found"}

    content = storage_service.download_file(artifact.storage_uri)
    return json.loads(content)


# ──────────────────────────────────────────────
# Phase 8 — Flow Discovery endpoints
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

    return {
        "run_id": run_id,
        "total": len(flows),
        "flows": [
            {
                "flow_id": f.id,
                "name": f.name,
                "flow_type": f.flow_type,
                "input_level": f.input_level,
                "start_state_id": f.start_state_id,
                "ordered_state_ids": f.ordered_state_ids_json.get("ids", []),
                "confidence": f.confidence,
                "confidence_label": f.confidence_label,
                "created_at": f.created_at,
            }
            for f in flows
        ]
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

    return {
        "flow_id": flow.id,
        "name": flow.name,
        "flow_type": flow.flow_type,
        "input_level": flow.input_level,
        "start_state_id": flow.start_state_id,
        "ordered_state_ids": flow.ordered_state_ids_json.get("ids", []),
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
                "hypothesized_action": t.hypothesized_action,
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
# Phase 9 — Missing Step Analysis endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/missing-step-report")
async def get_missing_step_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the full missing step analysis report from artifacts."""
    from app.db.models.artifact import Artifact
    from app.services.storage_service import storage_service
    from sqlalchemy import select
    import json

    result = await db.execute(
        select(Artifact).where(
            Artifact.run_id == run_id, 
            Artifact.artifact_type == "missing_step_analysis_report"
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        return {"error": "Report not found"}

    content = storage_service.download_file(artifact.storage_uri)
    return json.loads(content)


@router.get("/{run_id}/flows/{flow_id}/completeness")
async def get_flow_completeness(
    run_id: str,
    flow_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return completeness and eligibility data for a specific flow."""
    from app.db.models.flow import Flow
    from sqlalchemy import select
    from fastapi import HTTPException

    result = await db.execute(
        select(Flow).where(Flow.id == flow_id, Flow.run_id == run_id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    return {
        "flow_id": flow_id,
        "completeness_status": flow.completeness_status,
        "scenario_eligibility": flow.scenario_eligibility,
        "missing_step_penalty": flow.missing_step_penalty,
        "adjusted_confidence": flow.adjusted_confidence,
        "warnings": flow.missing_step_warnings_json,
    }


# ──────────────────────────────────────────────
# Phase 10 — Behaviour Intent Inference endpoints
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
                "intent_name": i.intent_name,
                "domain": i.behaviour_domain,
                "outcome": i.behaviour_outcome,
                "user_goal": i.user_goal,
                "confidence": i.confidence,
                "should_generate": i.should_generate,
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


# ──────────────────────────────────────────────
# Phase 11 — Behaviour Scenario Generation endpoints
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
        "title": scenario.scenario_title,
        "type": scenario.scenario_type,
        "grounding_mode": scenario.grounding_mode,
        "gherkin_text": scenario.gherkin_text,
        "structured_steps": scenario.structured_steps_json,
        "evidence": scenario.evidence_json,
        "assumptions": scenario.assumptions_json,
        "warnings": scenario.warnings_json,
        "confidence": scenario.initial_confidence,
        "status": scenario.status,
        "validation": {
            "status": scenario.validation_status,
            "grounding_score": scenario.grounding_score,
            "coverage_score": scenario.evidence_coverage_score,
            "hallucination_flags": scenario.hallucination_flags_json,
            "issues": scenario.validation_issues_json,
            "suggestions": scenario.revision_suggestions_json,
            "final_confidence": scenario.final_confidence,
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
# Phase 13 — Scenario Curation endpoints
# ──────────────────────────────────────────────

@router.get("/{run_id}/curated-scenarios")
async def list_curated_scenarios(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """List all curated scenarios for a run (accepted and accepted_with_warning)."""
    from app.db.models.behaviour_scenario import BehaviourScenario
    from sqlalchemy import select

    result = await db.execute(
        select(BehaviourScenario).where(
            BehaviourScenario.run_id == run_id,
            BehaviourScenario.final_status.in_(["accepted", "accepted_with_warning"])
        ).order_by(BehaviourScenario.final_priority, BehaviourScenario.final_confidence.desc())
    )
    scenarios = result.scalars().all()

    return {
        "run_id": run_id,
        "total": len(scenarios),
        "scenarios": [
            {
                "scenario_id": s.id,
                "title": s.scenario_title,
                "type": s.scenario_type,
                "final_status": s.final_status,
                "final_priority": s.final_priority,
                "final_confidence": s.final_confidence,
                "validation_status": s.validation_status
            }
            for s in scenarios
        ]
    }


@router.get("/{run_id}/scenario-curation-report")
async def get_scenario_curation_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the full scenario curation report from artifacts."""
    from app.db.models.artifact import Artifact
    from app.services.storage_service import storage_service
    from sqlalchemy import select
    import json

    result = await db.execute(
        select(Artifact).where(
            Artifact.run_id == run_id, 
            Artifact.artifact_type == "scenario_curation_report"
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        return {"error": "Report not found"}

    content = storage_service.download_file(artifact.storage_uri)
    return json.loads(content)


@router.get("/{run_id}/scenario-generation-report")
async def get_scenario_generation_report(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Return the full scenario generation report from artifacts."""
    from app.db.models.artifact import Artifact
    from app.services.storage_service import storage_service
    from sqlalchemy import select
    import json

    result = await db.execute(
        select(Artifact).where(
            Artifact.run_id == run_id, 
            Artifact.artifact_type == "behaviour_scenario_generation_report"
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        return {"error": "Report not found"}

    content = storage_service.download_file(artifact.storage_uri)
    return json.loads(content)

