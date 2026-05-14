"""
LangGraph node for Lightweight Preprocessing.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.lightweight_preprocessing_service import run_lightweight_preprocessing
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.core.logging import logger
from app.services.graph_progress import persist_run_graph_progress

async def lightweight_preprocessing_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "lightweight_preprocessing_node"
    await persist_run_graph_progress(run_id, node_name)
    
    try:
        if "raw_image_ids" not in state:
            reason = "MISSING_RAW_IMAGE_IDS"
            logger.error("[%s] %s for run %s (init_run_context likely failed).", node_name, reason, run_id)
            return {
                "current_node": node_name,
                "failed_nodes": [node_name],
                "errors": [f"{node_name}: {reason}"],
                "should_stop": True,
                "stop_reason": reason,
                "graph_status": "failed",
            }

        image_ids = state["raw_image_ids"]

        if is_active():
            log_node(
                node_name,
                intent_lines=[
                    "Mark images valid; ensure normalized_uri falls back to storage_uri.",
                    "routing: exact_duplicate unless should_stop from earlier.",
                ],
                state_keys=("run_id", "raw_image_ids", "config", "should_stop"),
                state=state,
            )

        result = await run_lightweight_preprocessing(db, run_id, image_ids)

        out = {
            "valid_images": result["valid_images"],
            "image_quality_report": result["report"],
            "preprocessing_warnings": result["warnings"],
            "current_node": node_name
        }
        if is_active():
            log_node_return(node_name, ["ok"], out)
        return out
    except Exception as e:
        logger.exception(f"[{node_name}] Error for run {run_id}: {e}")
        return {
            "current_node": node_name,
            "failed_nodes": [node_name],
            "errors": [f"{node_name}: {e}"],
            "should_stop": True,
            "stop_reason": f"CRITICAL_NODE_ERROR: {e}",
            "graph_status": "failed"
        }
