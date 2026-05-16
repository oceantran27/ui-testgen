"""
LangGraph node for Flow Context Builder (Agent 3).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.flow_context_builder_service import run_flow_context_builder
from app.core.logging import log_event, logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def flow_context_builder_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "flow_context_builder_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Build Flow State Cards from UI states and Screen Intents.",
            ],
            state_keys=("run_id",),
            state=state
        )
    
    try:
        state_catalog = state.get("state_catalog", [])
        screen_intent_pkg = state.get("screen_intent_package", {})
        screen_intent_catalog = screen_intent_pkg.get("screen_intent_catalog", [])

        if not state_catalog:
            return {
                "should_stop": True,
                "stop_reason": "NO_STATE_CATALOG",
                "graph_status": "failed"
            }
        
        result = await run_flow_context_builder(
            run_id=run_id, 
            state_catalog=state_catalog,
            screen_intent_catalog=screen_intent_catalog
        )

        out = {
            "flow_context_package": result,
            "current_node": node_name,
            "completed_nodes": [node_name],
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
