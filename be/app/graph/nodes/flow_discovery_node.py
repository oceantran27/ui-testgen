"""
Flow Discovery Node — LangGraph node for Phase 8.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.flow_discovery_service import FlowDiscoveryService

NODE_NAME = "flow_discovery"

async def flow_discovery_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 8 — Flow Discovery.
    Builds UI flows and transitions.
    """
    run_id = state["run_id"]
    state_catalog = state.get("state_catalog", [])
    input_level = state.get("detected_input_level", "Level 1")
    coarse_hints = state.get("coarse_flow_group_hints", [])
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await FlowDiscoveryService.run_discovery(
            db=db, 
            run_id=run_id, 
            state_catalog=state_catalog,
            input_level=input_level,
            coarse_flow_group_hints=coarse_hints
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Discovery failed: {result['error']}")
            return {
                "current_node": NODE_NAME,
                "failed_nodes": [NODE_NAME],
                "errors": [result["error"]],
                "should_stop": True,
                "graph_status": "failed"
            }

        updates: Dict[str, Any] = {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "detected_flows": result["detected_flows"],
            "ui_flow_graph": result["ui_flow_graph"],
            "flow_discovery_report": result["report"],
            "metrics": {
                f"{NODE_NAME}_flow_count": len(result["detected_flows"]),
            }
        }

        # Route to failure if no flows were discovered
        if not result["detected_flows"]:
             updates["should_stop"] = True
             updates["stop_reason"] = "NO_FLOWS_DETECTED"
             updates["graph_status"] = "failed"
             updates["errors"] = [f"[{NODE_NAME}] No UI flows could be discovered"]

        return updates

    except Exception as e:
        logger.exception(f"[{NODE_NAME}] Unexpected error for run {run_id}: {e}")
        return {
            "current_node": NODE_NAME,
            "failed_nodes": [NODE_NAME],
            "errors": [str(e)],
            "should_stop": True,
            "stop_reason": f"NODE_ERROR: {e}",
            "graph_status": "failed"
        }
