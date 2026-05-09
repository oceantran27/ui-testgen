"""
ARQ Worker — receives jobs from the Redis queue and executes the LangGraph pipeline.

Job: process_run
  1. Marks run status → processing
  2. Invokes graph_runner.run_pipeline(run_id)
  3. Marks run status → completed or failed based on result
"""
import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from datetime import datetime, timezone

from sqlalchemy import select

from app.services.queue_service import redis_settings
from app.core.logging import logger, log_event
from app.db.session import AsyncSessionLocal
from app.db.models.run import Run
from app.db.models.job import Job
from app.services.graph_service import GraphExecutionService


async def process_run(ctx, run_id: str):
    """Main worker job handler — executes the LangGraph pipeline via GraphExecutionService."""
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

    # ── 2. Execute pipeline ───────────────────
    try:
        await GraphExecutionService.execute(run_id=run_id, job_id=str(job_id))
        log_event("job_completed", run_id=run_id, job_id=job_id, node_name="worker")

    except Exception as e:
        logger.exception(f"Pipeline failed for run {run_id}: {e}", extra={"run_id": run_id})
        log_event("job_failed", run_id=run_id, job_id=job_id,
                  node_name="worker", error_code=str(e))


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
