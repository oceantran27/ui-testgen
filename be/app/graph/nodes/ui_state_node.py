"""
LangGraph node for UI State Extraction (Agent 1).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.ui_state_service import run_ui_state_extraction
from app.core.logging import log_event, logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def ui_state_extraction_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "ui_state_extraction_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Extract UI states from canonical screenshots.",
            ],
            state_keys=("run_id", "raw_image_ids"),
            state=state
        )
    
    try:
        image_ids = state.get("raw_image_ids", [])
        if not image_ids:
            return {
                "should_stop": True,
                "stop_reason": "NO_IMAGE_IDS",
                "graph_status": "failed"
            }
        
        result = await run_ui_state_extraction(db=db, run_id=run_id, image_ids=image_ids)

        out = {
            "ui_state_package": result,
            "state_catalog": result.get("extracted_states", []),
            "current_node": node_name,
            "completed_nodes": [node_name],
        }
        if is_active():
            log_node_return(node_name, ["ok"], out)
        return out
    except Exception as e:
        logger.exception(f"[{node_name}] Error for run {run_id}: {e}")
        await db.rollback()
        return {
            "current_node": node_name,
            "failed_nodes": [node_name],
            "errors": [f"{node_name}: {e}"],
            "should_stop": True,
            "stop_reason": f"CRITICAL_NODE_ERROR: {e}",
            "graph_status": "failed"
        }
