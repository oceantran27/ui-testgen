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
    from app.api.routes.runs import _uri_to_key
    from app.services.storage_service import storage_service
    object_key = _uri_to_key(artifact.storage_uri)
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
