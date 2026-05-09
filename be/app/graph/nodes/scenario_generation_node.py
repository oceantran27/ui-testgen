"""
Behaviour Scenario Generation Node — LangGraph node for Phase 11.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.scenario_generation_service import ScenarioGenerationService

NODE_NAME = "behaviour_scenario_generation"

async def behaviour_scenario_generation_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 11 — Behaviour Scenario Generation.
    Generates draft BDD scenarios using LLM.
    """
    run_id = state["run_id"]
    behaviour_intents = state.get("behaviour_intents", [])
    state_catalog = state.get("state_catalog", [])
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await ScenarioGenerationService.run_generation(
            db=db, 
            run_id=run_id, 
            behaviour_intents=behaviour_intents,
            state_catalog=state_catalog
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Generation failed: {result['error']}")
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
            "draft_scenarios": result["draft_scenarios"],
            "scenario_generation_report": result["report"],
        }

        if not result["draft_scenarios"]:
            logger.warning(f"[{NODE_NAME}] No scenarios were generated.")

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
