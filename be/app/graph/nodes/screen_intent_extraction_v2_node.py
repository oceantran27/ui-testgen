"""
LangGraph node for Screen Intent Extraction (Agent 2).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.screen_intent_service import run_screen_intent_extraction
from app.core.logging import log_event, logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def screen_intent_extraction_v2_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "screen_intent_extraction_v2_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Extract local screen intents from interaction groups.",
            ],
            state_keys=("run_id",),
            state=state
        )
    
    try:
        state_catalog = state.get("state_catalog", [])
        if not state_catalog:
            return {
                "should_stop": True,
                "stop_reason": "NO_STATE_CATALOG",
                "graph_status": "failed"
            }
        
        result = await run_screen_intent_extraction(db=db, run_id=run_id, state_catalog=state_catalog)

        out = {
            "screen_intent_package": result,
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
