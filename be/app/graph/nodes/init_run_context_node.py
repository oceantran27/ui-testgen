"""
Init Run Context Node — Phase 4 LangGraph entry point.
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.db.models.run import Run
from app.core.config import settings

NODE_NAME = "init_run_context_node"

async def init_run_context_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Initializes the graph state by reading run config from DB and setting up default metrics.
    """
    run_id = state["run_id"]
    log_event("graph_node_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        
        if not run:
            raise ValueError(f"Run {run_id} not found")

        config = run.config_json or {}
        
        # Merge system default config with run config
        merged_config = {
            "duplicate_allowed": settings.DUPLICATE_ALLOWED,
            "unordered_images_allowed": settings.UNORDERED_IMAGES_ALLOWED,
            "input_level_detection": settings.INPUT_LEVEL_DETECTION,
        }
        merged_config.update(config)

        log_event("graph_node_completed", run_id=run_id, node_name=NODE_NAME)

        return {
            "current_node": NODE_NAME,
            "config": merged_config,
            "graph_status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_nodes": [NODE_NAME],
            "metrics": {
                f"{NODE_NAME}_duration_ms": 0, # Placeholder, graph_runner handles actual timings if needed
            }
        }

    except Exception as e:
        logger.exception(f"[{NODE_NAME}] Error for run {run_id}: {e}")
        log_event("graph_node_failed", run_id=run_id, node_name=NODE_NAME, error_code=str(e))
        return {
            "current_node": NODE_NAME,
            "errors": [f"{NODE_NAME}: {e}"],
            "failed_nodes": [NODE_NAME],
            "should_stop": True,
            "stop_reason": f"NODE_ERROR: {e}",
            "graph_status": "failed"
        }
