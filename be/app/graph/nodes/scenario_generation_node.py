"""
LangGraph node for BDD Scenario Generation (Agent 6).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.core.logging import logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.scenario_generation_service import run_bdd_scenario_generation
from app.services.graph_progress import persist_run_graph_progress

async def behaviour_scenario_generation_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "behaviour_scenario_generation_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Synthesize BDD scenarios and Gherkin steps from intents.",
                "routing: scenario_evidence_audit unless error."
            ],
            state_keys=("run_id", "intent_package"),
            state=state
        )
    
    try:
        intent_package = state.get("intent_package") or {"behaviour_intents": []}

        result = await run_bdd_scenario_generation(
            db=db,
            run_id=run_id,
            intent_package=intent_package,
        )

        out = {
            "scenario_draft_package": result,
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
