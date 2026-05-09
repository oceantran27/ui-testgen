"""
Scenario Curation Node — LangGraph node for Phase 13.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.scenario_curation_service import ScenarioCurationService

NODE_NAME = "scenario_curation"

async def scenario_curation_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 13 — Scenario Curation.
    Deduplicates and prioritizes scenarios using LLM.
    """
    run_id = state["run_id"]
    
    # Collect all scenarios that passed validation (or low confidence ones)
    validated = state.get("validated_scenarios", [])
    low_confidence = state.get("low_confidence_scenarios", [])
    scenarios_to_curate = validated + low_confidence
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    if not scenarios_to_curate:
        logger.warning(f"[{NODE_NAME}] No scenarios available for curation.")
        return {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "curated_scenarios": [],
            "duplicate_scenario_groups": [],
            "scenario_curation_report": {"summary": {"input_count": 0}}
        }

    try:
        result = await ScenarioCurationService.run_curation(
            db=db, 
            run_id=run_id, 
            scenarios_to_curate=scenarios_to_curate
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Curation failed: {result['error']}")
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
            "curated_scenarios": result["curated_scenarios"],
            "duplicate_scenario_groups": result["duplicate_groups"],
            "scenario_curation_report": result["report"],
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
