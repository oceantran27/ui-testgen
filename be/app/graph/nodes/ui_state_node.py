"""
LangGraph node for UI State Extraction (Agent 1).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.ui_state_service import run_ui_state_extraction
from app.core.logging import log_event, logger
from app.services.graph_progress import persist_run_graph_progress

async def ui_state_extraction_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "ui_state_extraction_node"
    await persist_run_graph_progress(run_id, node_name)
    
    try:
        canonical_images = state.get("exact_canonical_images", [])
        if not canonical_images:
            return {
                "should_stop": True,
                "stop_reason": "NO_CANONICAL_IMAGES",
                "current_node": node_name
            }

        result = await run_ui_state_extraction(db=db, run_id=run_id, canonical_images=canonical_images)

        return {
            "ui_state_package": result,
            "state_catalog": result.get("extracted_states", []),
            "current_node": node_name,
            "completed_nodes": [node_name],
        }
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
