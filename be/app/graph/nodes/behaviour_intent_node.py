"""
LangGraph node for Behaviour Intent Inference (Agent 5).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.core.logging import log_event, logger
from app.services.behaviour_intent_service import run_behaviour_intent_inference
from app.services.graph_progress import persist_run_graph_progress

async def behaviour_intent_inference_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "behaviour_intent_inference_node"
    await persist_run_graph_progress(run_id, node_name)
    
    try:
        flow_discovery_result = state.get("flow_discovery_result")
        if not flow_discovery_result:
            # Fallback
            flow_discovery_result = {"flows": state.get("flow_clusters", [])}

        result = await run_behaviour_intent_inference(
            db=db,
            run_id=run_id,
            flow_discovery_result=flow_discovery_result
        )

        return {
            "intent_package": result,
            "current_node": node_name,
            "completed_nodes": [node_name]
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
