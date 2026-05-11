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
from app.core.pipeline_run_log import is_active, log_node, log_node_return, console_err

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

    if is_active():
        log_node(
            NODE_NAME,
            intent_lines=[
                "Load Run row and Image rows; merge run.config with defaults.",
                "routing: always lightweight_preprocessing unless error (should_stop).",
            ],
            state_keys=("run_id", "job_id"),
            state=state,
        )

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

        # Load raw images
        from app.db.models.image import Image
        img_result = await db.execute(
            select(Image)
            .where(Image.run_id == run_id)
            .order_by(Image.upload_order.asc())
        )
        images = list(img_result.scalars().all())
        raw_image_ids = [img.id for img in images]

        log_event("graph_node_completed", run_id=run_id, node_name=NODE_NAME)

        out = {
            "current_node": NODE_NAME,
            "config": merged_config,
            "raw_image_ids": raw_image_ids,
            "graph_status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_nodes": [NODE_NAME],
            "metrics": {
                f"{NODE_NAME}_duration_ms": 0, # Placeholder, graph_runner handles actual timings if needed
            }
        }
        if is_active():
            log_node_return(NODE_NAME, ["ok"], out)
        return out

    except Exception as e:
        logger.exception(f"[{NODE_NAME}] Error for run {run_id}: {e}")
        log_event("graph_node_failed", run_id=run_id, node_name=NODE_NAME, error_code=str(e))
        fail = {
            "current_node": NODE_NAME,
            "errors": [f"{NODE_NAME}: {e}"],
            "failed_nodes": [NODE_NAME],
            "should_stop": True,
            "stop_reason": f"NODE_ERROR: {e}",
            "graph_status": "failed"
        }
        if is_active():
            console_err(f"{NODE_NAME}: {e}")
            log_node_return(NODE_NAME, ["failed"], fail)
        return fail
