"""
Graph Execution Service — Phase 4 orchestration.
"""
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings
from app.core.logging import logger, log_event
from app.db.session import AsyncSessionLocal
from app.db.models.run import Run
from app.graph.runner.graph_runner import build_graph
from app.graph.state.graph_state import PipelineState
from app.model_providers.db_session_context import model_call_db_session, model_call_job_id


def _be_root() -> Path:
    """Backend package root (`be/`), i.e. parent of `app/`."""
    return Path(__file__).resolve().parents[2]


def _postgres_checkpoint_conninfo(database_url: str) -> str:
    """SQLAlchemy async URLs use postgresql+asyncpg://; libpq/psycopg expect postgresql://."""
    url = database_url.strip()
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


CHECKPOINT_URI = _postgres_checkpoint_conninfo(settings.DATABASE_URL)


class GraphExecutionService:

    @staticmethod
    async def execute(run_id: str, job_id: str | None = None) -> dict:
        """
        Executes the LangGraph pipeline for a specific run_id.
        Handles state initialization, checkpointing, and DB status updates.
        """
        log_event("pipeline_execution_started", run_id=run_id, job_id=job_id)

        # 1. Update DB: Set to processing
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one_or_none()
            if not run:
                logger.error(f"Run {run_id} not found.")
                return {}

            run.status = "processing"
            run.graph_status = "running"
            run.current_phase = "processing"
            run.graph_started_at = datetime.now(timezone.utc)
            # Create a thread_id for this execution if not exists
            if not run.graph_thread_id:
                run.graph_thread_id = run_id
            thread_id = run.graph_thread_id
            await db.commit()

        # 2. Setup initial state
        initial_state: PipelineState = {
            "run_id": run_id,
            "job_id": job_id,
        }

        config = {"configurable": {"thread_id": thread_id}}

        pipeline_log_active = False
        if settings.PIPELINE_RUN_LOG_ENABLED:
            from app.core import pipeline_run_log as prl

            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            session_dir = _be_root() / settings.PIPELINE_RUN_LOG_ROOT / f"{ts}_{run_id}"
            prl.activate(run_id, session_dir)
            pipeline_log_active = True

        def _timing_file(note: str, **fields: object) -> None:
            if not (settings.PIPELINE_RUN_LOG_ENABLED and pipeline_log_active):
                return
            from app.core import pipeline_run_log as prl

            if prl.is_active():
                prl.file_detail(
                    "pipeline_timing",
                    [note, *[f"{k}={v}" for k, v in fields.items()]],
                )

        try:
            # 3. Execute Graph
            try:
                # We open a DB session to pass to the graph nodes
                async with AsyncSessionLocal() as db:
                    db_tok = model_call_db_session.set(db)
                    job_tok = model_call_job_id.set(job_id)
                    try:
                        graph = build_graph(db=db)
                        t0 = time.perf_counter()

                        # Use checkpointer if enabled
                        if settings.ENABLE_GRAPH_CHECKPOINT:
                            try:
                                t_cp0 = time.perf_counter()
                                async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_URI) as checkpointer:
                                    await checkpointer.setup()
                                    t_cp1 = time.perf_counter()
                                    ms = int((t_cp1 - t_cp0) * 1000)
                                    logger.debug(
                                        "graph_checkpoint_ready_ms=%d run_id=%s",
                                        ms,
                                        run_id,
                                    )
                                    _timing_file("graph_checkpoint_ready", ms=ms, run_id=run_id)
                                    graph.checkpointer = checkpointer
                                    compiled = graph.compile()
                                    t_inv0 = time.perf_counter()
                                    final_state = await compiled.ainvoke(initial_state, config=config)
                                    t_inv1 = time.perf_counter()
                                    ms_inv = int((t_inv1 - t_inv0) * 1000)
                                    logger.debug(
                                        "graph_ainvoke_ms=%d run_id=%s",
                                        ms_inv,
                                        run_id,
                                    )
                                    _timing_file("graph_ainvoke", ms=ms_inv, run_id=run_id)
                            except Exception as cp_err:
                                from app.core import pipeline_run_log as prl

                                msg = (
                                    "Failed to initialize PostgreSQL checkpointer, "
                                    f"falling back to MemorySaver: {cp_err}"
                                )
                                if prl.is_active():
                                    prl.console_warn(msg)
                                else:
                                    logger.warning(msg)
                                t_fb0 = time.perf_counter()
                                from langgraph.checkpoint.memory import MemorySaver

                                checkpointer = MemorySaver()
                                graph.checkpointer = checkpointer
                                compiled = graph.compile()
                                final_state = await compiled.ainvoke(initial_state, config=config)
                                t_fb1 = time.perf_counter()
                                ms_fb = int((t_fb1 - t_fb0) * 1000)
                                logger.debug(
                                    "graph_ainvoke_memory_checkpoint_ms=%d run_id=%s",
                                    ms_fb,
                                    run_id,
                                )
                                _timing_file("graph_ainvoke_memory_checkpoint", ms=ms_fb, run_id=run_id)
                        else:
                            compiled = graph.compile()
                            t_inv0 = time.perf_counter()
                            final_state = await compiled.ainvoke(initial_state, config=config)
                            t_inv1 = time.perf_counter()
                            ms_nc = int((t_inv1 - t_inv0) * 1000)
                            logger.debug(
                                "graph_ainvoke_no_checkpoint_ms=%d run_id=%s",
                                ms_nc,
                                run_id,
                            )
                            _timing_file("graph_ainvoke_no_checkpoint", ms=ms_nc, run_id=run_id)

                        total_ms = int((time.perf_counter() - t0) * 1000)
                        logger.debug(
                            "graph_execute_total_ms=%d run_id=%s",
                            total_ms,
                            run_id,
                        )
                        _timing_file("graph_execute_total", ms=total_ms, run_id=run_id)

                        log_event("pipeline_execution_completed", run_id=run_id, job_id=job_id)
                        return final_state
                    finally:
                        model_call_db_session.reset(db_tok)
                        model_call_job_id.reset(job_tok)

            except Exception as e:
                if pipeline_log_active:
                    from app.core import pipeline_run_log as prl

                    if prl.is_active():
                        prl.console_err(f"Pipeline error for run {run_id}: {e}")
                logger.exception("Pipeline error for run %s: %s", run_id, e)
                log_event(
                    "pipeline_execution_error",
                    run_id=run_id,
                    job_id=job_id,
                    error_code=str(e),
                    level=logging.ERROR,
                )

                # Final fallback update if graph finalizer couldn't run
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(Run).where(Run.id == run_id))
                    run = result.scalar_one_or_none()
                    if run:
                        run.status = "failed"
                        run.graph_status = "failed"
                        run.error_message = str(e)[:500]
                        run.graph_completed_at = datetime.now(timezone.utc)
                        await db.commit()
                raise

        finally:
            if pipeline_log_active:
                from app.core import pipeline_run_log as prl

                prl.deactivate()
