"""
ARQ Worker — receives jobs from the Redis queue and executes the LangGraph pipeline.

Job: process_run
  1. Marks run status → processing
  2. Invokes graph_runner.run_pipeline(run_id)
  3. Marks run status → completed or failed based on result
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.services.queue_service import redis_settings
from app.core.logging import logger, log_event
from app.db.session import AsyncSessionLocal
from app.db.models.run import Run
from app.db.models.job import Job
from app.graph.runner.graph_runner import run_pipeline


async def process_run(ctx, run_id: str):
    """Main worker job handler — runs the full LangGraph pipeline for a given run."""
    job_id = ctx.get("job_id", "unknown")
    log_event("job_started", run_id=run_id, job_id=job_id, node_name="worker")

    async with AsyncSessionLocal() as db:
        # ── 1. Load and guard run ─────────────
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()

        if not run:
            logger.error(f"Run {run_id} not found in database.", extra={"run_id": run_id})
            return

        if run.status not in ("queued",):
            logger.warning(
                f"Run {run_id} is in status '{run.status}', expected 'queued'. Skipping.",
                extra={"run_id": run_id},
            )
            return

        # ── 2. Mark processing ────────────────
        run.status = "processing"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

    # ── 3. Execute pipeline ───────────────────
    # The pipeline opens its own session internally (via graph_runner).
    try:
        final_state = await run_pipeline(run_id=run_id, job_id=str(job_id))

        # ── 4. Update run status based on result ─
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one_or_none()

            if run:
                # If pipeline already set run.status = failed (e.g. NO_VALID_IMAGES),
                # respect that; otherwise mark completed.
                if run.status not in ("failed",):
                    if final_state.get("should_stop"):
                        run.status = "failed"
                        run.error_message = final_state.get("stop_reason", "PIPELINE_STOPPED")
                    else:
                        run.status = "completed"

                run.completed_at = datetime.now(timezone.utc)
                await db.commit()

        log_event("job_completed", run_id=run_id, job_id=job_id, node_name="worker")

    except Exception as e:
        logger.exception(f"Pipeline failed for run {run_id}: {e}", extra={"run_id": run_id})
        log_event("job_failed", run_id=run_id, job_id=job_id,
                  node_name="worker", error_code=str(e))

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one_or_none()
            if run:
                run.status = "failed"
                run.error_message = str(e)[:500]
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()


# ──────────────────────────────────────────────
# Worker lifecycle hooks
# ──────────────────────────────────────────────

async def startup(ctx):
    logger.info("Worker starting up...")


async def shutdown(ctx):
    logger.info("Worker shutting down...")


# ──────────────────────────────────────────────
# Worker settings (used by ARQ)
# ──────────────────────────────────────────────

class WorkerSettings:
    functions = [process_run]
    redis_settings = redis_settings
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 2


if __name__ == "__main__":
    from arq import run_worker
    run_worker(WorkerSettings)
