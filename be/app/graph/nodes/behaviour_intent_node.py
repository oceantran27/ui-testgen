"""
LangGraph node for Behaviour Intent Inference (Agent 5).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.core.logging import log_event, logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.behaviour_intent_service import run_behaviour_intent_inference
from app.services.graph_progress import persist_run_graph_progress

async def behaviour_intent_inference_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "behaviour_intent_inference_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Infer user intents and business goals from discovered flows.",
                "routing: behaviour_scenario_generation unless error."
            ],
            state_keys=("run_id", "flow_discovery_result"),
            state=state
        )
    
    try:
        flow_discovery_result = state.get("flow_discovery_result")
        if not flow_discovery_result:
            # Fallback
            flow_discovery_result = {"candidate_flows": state.get("flow_clusters", [])}

        result = await run_behaviour_intent_inference(
            db=db,
            run_id=run_id,
            flow_discovery_result=flow_discovery_result
        )

        out = {
            "intent_package": result,
            "current_node": node_name,
            "completed_nodes": [node_name]
        }
        if is_active():
            log_node_return(node_name, ["ok"], out)
        return out
    except Exception as e:
        logger.exception(f"[{node_name}] Error for run {run_id}: {e}")
        try:
            await db.rollback()
        except Exception as rb_err:
            logger.warning(f"[{node_name}] Double fault during rollback: {rb_err}")
            
        return {
            "current_node": node_name,
            "failed_nodes": [node_name],
            "errors": [f"{node_name}: {e}"],
            "should_stop": True,
            "stop_reason": f"CRITICAL_NODE_ERROR: {e}",
            "graph_status": "failed"
        }
