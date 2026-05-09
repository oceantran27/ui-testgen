"""
Input Level Detection Node — LangGraph node for Phase 7.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.input_level_service import InputLevelService

NODE_NAME = "input_level_detection"

async def input_level_detection_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 7 — Input Level Detection.
    Classifies input into Level 1, 2, or 3.
    """
    run_id = state["run_id"]
    state_catalog = state.get("state_catalog", [])
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await InputLevelService.run_detection(
            db=db, 
            run_id=run_id, 
            state_catalog=state_catalog
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Detection failed: {result['error']}")
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
            "detected_input_level": result["detected_input_level"],
            "input_level_confidence": result["input_level_confidence"],
            "coarse_flow_group_hints": result["coarse_flow_group_hints"],
            "input_level_detection_report": result["report"],
            "warnings": [w["message"] for w in result.get("warnings", [])],
        }

        return updates

    except Exception as e:
        logger.exception(f"[{NODE_NAME}] Unexpected error for run {run_id}: {e}")
        return {
            "current_node": NODE_NAME,
            "failed_nodes": [NODE_NAME],
            "errors": [str(e)],
            "should_stop": True,
            "graph_status": "failed"
        }
