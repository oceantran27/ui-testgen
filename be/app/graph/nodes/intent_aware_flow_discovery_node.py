"""
LangGraph node for Intent-Aware Flow Discovery (Agent 4).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.intent_aware_flow_discovery_service import run_intent_aware_flow_discovery
from app.core.logging import log_event, logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def intent_aware_flow_discovery_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "intent_aware_flow_discovery_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Discover intent-aware flows from Flow State Cards.",
            ],
            state_keys=("run_id",),
            state=state
        )
    
    try:
        flow_context_package = state.get("flow_context_package", {})
        if not flow_context_package:
            return {
                "should_stop": True,
                "stop_reason": "NO_FLOW_CONTEXT_PACKAGE",
                "graph_status": "failed"
            }
        
        result = await run_intent_aware_flow_discovery(db=db, run_id=run_id, flow_context_package=flow_context_package)

        out = {
            "flow_discovery_result": result,
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
