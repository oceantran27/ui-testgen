"""
LangGraph node for Behaviour Contract Builder (Agent 5).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.behaviour_contract_service import run_behaviour_contract_builder
from app.core.logging import logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def behaviour_contract_builder_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "behaviour_contract_builder_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Build formal Behaviour Contracts from discovered flows.",
            ],
            state_keys=("run_id",),
            state=state
        )
    
    try:
        flow_discovery_result = state.get("flow_discovery_result", {})
        state_catalog = state.get("state_catalog", [])
        
        if not flow_discovery_result:
            return {
                "should_stop": True,
                "stop_reason": "NO_FLOW_DISCOVERY_RESULT",
                "graph_status": "failed"
            }
        
        result = await run_behaviour_contract_builder(
            db=db, 
            run_id=run_id, 
            flow_discovery_result=flow_discovery_result,
            state_catalog=state_catalog
        )

        out = {
            "intent_package": result,
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
