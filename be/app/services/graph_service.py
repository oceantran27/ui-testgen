"""
Graph Execution Service — Phase 4 orchestration.
"""
from datetime import datetime, timezone
from sqlalchemy import select

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.core.logging import logger, log_event
from app.db.session import AsyncSessionLocal
from app.db.models.run import Run
from app.graph.runner.graph_runner import build_graph
from app.graph.state.graph_state import PipelineState

# Prepare the checkpointer connection URI
CHECKPOINT_URI = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://")

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

        # 3. Execute Graph
        try:
            # We open a DB session to pass to the graph nodes
            async with AsyncSessionLocal() as db:
                graph = build_graph(db=db)
                
                # Use checkpointer if enabled
                if settings.ENABLE_GRAPH_CHECKPOINT:
                    try:
                        async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_URI) as checkpointer:
                            await checkpointer.setup()
                            graph.checkpointer = checkpointer
                            compiled = graph.compile()
                            final_state = await compiled.ainvoke(initial_state, config=config)
                    except Exception as cp_err:
                        logger.warning(f"Failed to initialize PostgreSQL checkpointer, falling back to MemorySaver: {cp_err}")
                        from langgraph.checkpoint.memory import MemorySaver
                        checkpointer = MemorySaver()
                        graph.checkpointer = checkpointer
                        compiled = graph.compile()
                        final_state = await compiled.ainvoke(initial_state, config=config)
                else:
                    compiled = graph.compile()
                    final_state = await compiled.ainvoke(initial_state, config=config)
                
                log_event("pipeline_execution_completed", run_id=run_id, job_id=job_id)
                return final_state

        except Exception as e:
            logger.exception(f"Pipeline error for run {run_id}: {e}")
            log_event("pipeline_execution_error", run_id=run_id, job_id=job_id, error_code=str(e))
            
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
