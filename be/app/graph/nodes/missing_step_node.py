"""
Missing Step Analysis Node — LangGraph node for Phase 9.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.missing_step_service import MissingStepService

NODE_NAME = "missing_step_analysis"

async def missing_step_analysis_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 9 — Missing Step Analysis.
    Analyzes flow completeness and assigns penalties.
    """
    run_id = state["run_id"]
    flow_ids = state.get("detected_flows", [])
    state_catalog = state.get("state_catalog", [])
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await MissingStepService.run_analysis(
            db=db, 
            run_id=run_id, 
            flow_ids=flow_ids,
            state_catalog=state_catalog
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Analysis failed: {result['error']}")
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
            "missing_step_report": result["missing_step_report"],
            "flow_completeness_results": result["flow_completeness_results"],
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
