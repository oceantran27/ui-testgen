"""
LangGraph node for BDD Scenario Generation (Agent 6).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.scenario_generation_service import run_bdd_scenario_generation
from app.services.graph_progress import persist_run_graph_progress

async def behaviour_scenario_generation_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    await persist_run_graph_progress(run_id, "behaviour_scenario_generation_node")
    
    intent_package = state.get("intent_package")
    if not intent_package:
        # Fallback
        intent_package = {"flow_intents": state.get("behaviour_intents", [])}

    result = await run_bdd_scenario_generation(
        db=db,
        run_id=run_id,
        intent_package=intent_package
    )

    return {
        "scenario_draft_package": result,
        "current_node": "behaviour_scenario_generation_node",
        "completed_nodes": ["behaviour_scenario_generation_node"]
    }
