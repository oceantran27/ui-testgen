"""
Run Service — business logic for run lifecycle management.

Handles: create, get, submit, cancel, list.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger, log_event
from app.core.errors import (
    RunNotFoundException,
    RunNotUploadableException,
    RunAlreadySubmittedException,
    RunHasNoImagesException,
    RunNotCancellableException,
    StorageUploadFailedException,
)
from app.db.session import AsyncSessionLocal
from app.db.models.run import Run
from app.db.models.image import Image
from app.db.models.job import Job
from app.db.models.artifact import Artifact
from app.schemas.run import RunConfig
from app.services.queue_service import queue_service
from app.services.storage_service import storage_service


# ──────────────────────────────────────────────
# ID generation helpers
# ──────────────────────────────────────────────

def _generate_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _generate_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


# Statuses that still allow image uploads
UPLOADABLE_STATUSES = {"created", "uploading"}

# Statuses from which a run can be submitted
SUBMITTABLE_STATUSES = {"created", "uploading"}

# Statuses from which a run can be cancelled
CANCELLABLE_STATUSES = {"created", "uploading", "uploaded", "queued"}


# ──────────────────────────────────────────────
# Service functions
# ──────────────────────────────────────────────

async def create_run(
    db: AsyncSession,
    project_name: Optional[str] = None,
    description: Optional[str] = None,
    config: Optional[RunConfig] = None,
) -> Run:
    """Create a new processing run with optional config overrides."""
    run_id = _generate_run_id()
    run_config = config or RunConfig()

    run = Run(
        id=run_id,
        project_name=project_name,
        description=description,
        status="created",
        total_images=0,
        valid_images=0,
        invalid_images=0,
        config_json=run_config.model_dump(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    log_event("run_created", run_id=run_id)
    return run


async def mark_run_failed_worker(run_id: str, error_message: str, max_len: int = 500) -> None:
    """
    Persist failed status when the worker job is cancelled (e.g. ARQ timeout) and
    GraphExecutionService did not update the row. Idempotent: does not overwrite completed.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            return
        if run.status in ("completed", "cancelled", "failed"):
            return
        run.status = "failed"
        run.graph_status = "failed"
        run.error_message = (error_message or "Run failed")[:max_len]
        run.graph_completed_at = datetime.now(timezone.utc)
        await db.commit()
        log_event("run_marked_failed_worker", run_id=run_id, error_code=run.error_message[:80])


async def get_run(db: AsyncSession, run_id: str) -> Run:
    """Fetch a run by ID. Raises RunNotFoundException if missing."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise RunNotFoundException(run_id)
    return run


async def list_runs(db: AsyncSession) -> List[Run]:
    """Return all runs ordered by creation time desc."""
    result = await db.execute(select(Run).order_by(Run.created_at.desc()))
    return list(result.scalars().all())


async def submit_run(db: AsyncSession, run_id: str) -> dict:
    """
    Submit a run for processing.

    Flow:
    1. Validate run exists and is in a submittable state.
    2. Ensure at least one image is uploaded.
    3. Transition status: uploaded → queued.
    4. Generate and save input_manifest.json artifact.
    5. Create a Job record and enqueue it.
    """
    run = await get_run(db, run_id)

    # Guard: status check
    if run.status not in SUBMITTABLE_STATUSES:
        if run.status in {"queued", "processing", "completed", "uploaded"}:
            raise RunAlreadySubmittedException(run_id)
        raise RunNotUploadableException(run_id, run.status)

    # Guard: must have images
    if run.total_images == 0:
        raise RunHasNoImagesException(run_id)

    now = datetime.now(timezone.utc)

    # ── Transition to uploaded ───────────────
    run.status = "uploaded"
    run.submitted_at = now
    await db.flush()

    # ── Build & save input_manifest.json ─────
    await _save_input_manifest(db, run)

    # ── Create job record ────────────────────
    job_id = _generate_job_id()
    job = Job(
        id=job_id,
        run_id=run_id,
        job_type="process_run",
        status="queued",
        queue_name="default",
        attempt_count=0,
        max_attempts=3,
    )
    db.add(job)

    # ── Enqueue ──────────────────────────────
    await queue_service.enqueue_job("process_run", run_id=run_id)

    run.status = "queued"
    await db.commit()

    log_event("run_submitted", run_id=run_id)
    log_event("job_created", run_id=run_id, job_id=job_id)
    log_event("job_enqueued", run_id=run_id, job_id=job_id)

    return {"run_id": run_id, "status": "queued", "job_id": job_id, "message": "Run submitted and job enqueued."}


async def cancel_run(db: AsyncSession, run_id: str) -> dict:
    """Cancel a run if it has not started processing yet."""
    run = await get_run(db, run_id)

    if run.status not in CANCELLABLE_STATUSES:
        raise RunNotCancellableException(run_id, run.status)

    run.status = "cancelled"
    await db.commit()

    log_event("run_cancelled", run_id=run_id)
    return {"run_id": run_id, "status": "cancelled", "message": "Run cancelled successfully."}


async def delete_run(db: AsyncSession, run_id: str) -> bool:
    """Hard delete a run and its related records (cascaded in DB)."""
    run = await get_run(db, run_id)
    await db.delete(run)
    await db.commit()
    log_event("run_deleted", run_id=run_id)
    return True


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

async def _save_input_manifest(db: AsyncSession, run: Run) -> None:
    """Create input_manifest.json artifact and save it to object storage."""
    result = await db.execute(
        select(Image)
        .where(Image.run_id == run.id)
        .order_by(Image.upload_order.asc())
    )
    images = list(result.scalars().all())

    manifest = {
        "run_id": run.id,
        "config": run.config_json,
        "total_images": len(images),
        "upload_summary": {
            "total_uploaded": len(images),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "images": [
            {
                "image_id": img.id,
                "original_filename": img.original_filename,
                "storage_uri": img.storage_uri,
                "format": img.format,
                "file_size": img.file_size,
                "width": img.width,
                "height": img.height,
                "upload_order": img.upload_order,
                "sha256_hash": img.sha256_hash,
            }
            for img in images
        ],
    }

    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False, default=str).encode(
        "utf-8"
    )
    object_key = f"artifacts/{run.id}/input_intake/input_manifest.json"
    try:
        storage_uri = storage_service.upload_file(
            file_content=manifest_bytes,
            object_name=object_key,
            content_type="application/json",
        )
    except ClientError as e:
        raise StorageUploadFailedException(
            "input_manifest.json", reason=str(e)
        ) from e

    artifact = Artifact(
        id=_generate_artifact_id(),
        run_id=run.id,
        artifact_type="input_manifest",
        node_name="input_intake",
        storage_uri=storage_uri,
        metadata_json={"total_images": len(images)},
    )
    db.add(artifact)
    await db.flush()

    log_event("artifact_saved", run_id=run.id, node_name="input_intake")
