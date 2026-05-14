"""
LangGraph node for UI Flow Discovery (Agent 3).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.llm_flow_discovery_service import run_ui_flow_discovery
from app.core.logging import log_event, logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def llm_flow_discovery_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "llm_flow_discovery_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Infer user flows and transitions from canonical states.",
                "routing: behaviour_intent_inference unless error."
            ],
            state_keys=("run_id", "canonical_state_set"),
            state=state
        )
    
    try:
        canonical_state_set = state.get("canonical_state_set")
        if not canonical_state_set:
            # Fallback for transition compatibility
            canonical_state_set = {"unique_states": state.get("canonical_state_catalog", [])}

        result = await run_ui_flow_discovery(
            db=db,
            run_id=run_id,
            canonical_state_set=canonical_state_set
        )

        out = {
            "flow_discovery_result": result,
            "flow_clusters": result.get("candidate_flows", []),
            "unassigned_state_ids": [], # Schema changed, this is now handled within candidate_flows or clusters
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
