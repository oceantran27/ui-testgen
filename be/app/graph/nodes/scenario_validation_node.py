"""
LangGraph node for Scenario Validation (Agent 7).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.scenario_validation_service import run_scenario_validation
from app.core.logging import log_event, logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def scenario_validation_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "scenario_validation_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Audit BDD scenarios against UI evidence and flows.",
                "routing: output_assembly unless error."
            ],
            state_keys=("run_id", "scenario_draft_package"),
            state=state
        )
    
    try:
        scenario_draft_package = state.get("scenario_draft_package")
        if not scenario_draft_package:
            # Fallback
            scenario_draft_package = {"features": state.get("draft_scenarios", [])}

        result = await run_scenario_validation(
            db=db,
            run_id=run_id,
            scenario_draft_package=scenario_draft_package,
            ui_state_package=state.get("ui_state_package"),
            flow_discovery_result=state.get("flow_discovery_result"),
            intent_package=state.get("intent_package")
        )

        out = {
            "validated_scenario_package": result,
            "current_node": node_name,
            "completed_nodes": [node_name]
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
