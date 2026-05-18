"""
ARQ Worker — receives jobs from the Redis queue and executes the LangGraph pipeline.

Job: process_run
  1. Run row is set to processing inside GraphExecutionService
  2. GraphExecutionService.execute(run_id, job_id) runs the compiled LangGraph
  3. graph_finalizer_node sets run/job status to completed or failed
"""
import asyncio
import json
import sys
from datetime import timedelta

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select

from app.services.queue_service import redis_settings
from app.core.config import settings
from app.core.logging import logger, log_event
from app.db.session import AsyncSessionLocal
from app.db.models.run import Run
from app.services.graph_service import GraphExecutionService
from app.services.run_service import mark_run_failed_worker
from arq.worker import func

_ARQ_AMBIGUOUS_300_WARN_EMITTED = False


def _arq_worker_job_timedelta() -> timedelta:
    """
    ARQ wraps each job with asyncio.wait_for; default Worker job_timeout is 300s unless overridden.
    Use timedelta.max for no practical deadline (preferred over None — ARQ 0.28 max_timeout math).
    """
    global _ARQ_AMBIGUOUS_300_WARN_EMITTED
    if settings.ARQ_JOB_NO_TIMEOUT or settings.ARQ_JOB_TIMEOUT_SECONDS <= 0:
        # Use a very large but safe duration (7 days) instead of timedelta.max to avoid asyncio overflows
        return timedelta(days=7)
    raw = settings.ARQ_JOB_TIMEOUT_SECONDS
    if getattr(settings, "ARQ_INTERPRET_300S_AS_LONG_JOB", True) and int(raw) == 300:
        fb = getattr(settings, "ARQ_JOB_LONG_PIPELINE_FALLBACK_SECONDS", 14400)
        if not _ARQ_AMBIGUOUS_300_WARN_EMITTED:
            _ARQ_AMBIGUOUS_300_WARN_EMITTED = True
            logger.warning(
                "ARQ_JOB_TIMEOUT_SECONDS=%s matches ARQ's built-in job default (300s). "
                "Treating as ambiguous for long pipelines; using %ss for process_run timeouts instead. "
                "Set ARQ_INTERPRET_300S_AS_LONG_JOB=false to keep Wall=300s, or set "
                "ARQ_JOB_TIMEOUT_SECONDS to an explicit limit (e.g. 7200).",
                raw,
                fb,
                extra={
                    "event_name": "worker_arq_timeout_300_interpreted_as_long_job",
                    "node_name": "worker",
                },
            )
        return timedelta(seconds=fb)
    return timedelta(seconds=raw)


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

    except asyncio.CancelledError:
        # ARQ job timeout cancels the task; CancelledError is not a subclass of Exception.
        log_event(
            "job_cancelled",
            run_id=run_id,
            job_id=job_id,
            node_name="worker",
            error_code="CancelledError",
        )
        await mark_run_failed_worker(
            run_id,
            "Job cancelled or worker-level timeout (exceeded ARQ job_timeout).",
        )
        raise

    except Exception as e:
        logger.exception(f"Pipeline failed for run {run_id}: {e}", extra={"run_id": run_id})
        log_event("job_failed", run_id=run_id, job_id=job_id,
                  node_name="worker", error_code=str(e))


# ──────────────────────────────────────────────
# Worker lifecycle hooks
# ──────────────────────────────────────────────

async def startup(ctx):
    resolved = _arq_worker_job_timedelta()
    unlimited = settings.ARQ_JOB_NO_TIMEOUT or settings.ARQ_JOB_TIMEOUT_SECONDS <= 0
    logger.info(
        "Worker startup ARQ_JOB_NO_TIMEOUT=%s ARQ_JOB_TIMEOUT_SECONDS=%s resolved_job_timeout=%s",
        settings.ARQ_JOB_NO_TIMEOUT,
        settings.ARQ_JOB_TIMEOUT_SECONDS,
        ("unlimited timedelta.max" if unlimited else f"{resolved.total_seconds():.0f}s"),
    )
    _fn_spec = WorkerSettings.functions[0]
    _fto = getattr(_fn_spec, "timeout_s", None)
    _diag = {
        "worker_job_timeout_s": WorkerSettings.job_timeout.total_seconds(),
        "function_process_run_timeout_s": _fto,
        "settings_ARQ_JOB_TIMEOUT_SECONDS": settings.ARQ_JOB_TIMEOUT_SECONDS,
        "arq_interpret_300s_as_long_job": getattr(
            settings, "ARQ_INTERPRET_300S_AS_LONG_JOB", True
        ),
        "resolved_wall_seconds_after_interpret": resolved.total_seconds(),
        "DISABLE_MODEL_CALL_ASYNCIO_TIMEOUT": getattr(
            settings, "DISABLE_MODEL_CALL_ASYNCIO_TIMEOUT", None
        ),
    }
    logger.info(
        "Event diagnostic worker_arq_timeout_proof_json=%s",
        json.dumps(_diag, ensure_ascii=False),
        extra={"event_name": "worker_arq_timeout_proof", "node_name": "worker"},
    )
    if (
        not getattr(settings, "ARQ_INTERPRET_300S_AS_LONG_JOB", True)
        and not settings.ARQ_JOB_NO_TIMEOUT
        and settings.ARQ_JOB_TIMEOUT_SECONDS > 0
        and int(settings.ARQ_JOB_TIMEOUT_SECONDS) == 300
    ):
        logger.warning(
            "ARQ_JOB_TIMEOUT_SECONDS resolves to exactly 300s (matches ARQ default). "
            "If unintended, enable ARQ_INTERPRET_300S_AS_LONG_JOB=true, remove "
            "ARQ_JOB_TIMEOUT_SECONDS from .env, or set ARQ_JOB_NO_TIMEOUT=true.",
            extra={"event_name": "worker_arq_timeout_suspected_misconfiguration", "node_name": "worker"},
        )


async def shutdown(ctx):
    logger.info("Worker shutting down...")


# ──────────────────────────────────────────────
# Worker settings (used by ARQ)
# ──────────────────────────────────────────────

# Single resolved deadline for ARQ (Worker.job_timeout AND per-job func timeout below).
_arq_job_timeout_td = _arq_worker_job_timedelta()


class WorkerSettings:
    functions = [func(process_run, timeout=_arq_job_timeout_td)]
    redis_settings = redis_settings
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 2
    job_timeout = _arq_job_timeout_td


if __name__ == "__main__":
    from arq import run_worker
    run_worker(WorkerSettings)
