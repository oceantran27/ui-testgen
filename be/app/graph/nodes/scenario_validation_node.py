"""
Scenario Grounding & Validation Node — LangGraph node for Phase 12.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.scenario_validation_service import ScenarioValidationService

NODE_NAME = "scenario_validation"

async def scenario_validation_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 12 — Scenario Grounding & Validation.
    Validates draft BDD scenarios using LLM-as-a-Judge.
    """
    run_id = state["run_id"]
    draft_scenarios = state.get("draft_scenarios", [])
    state_catalog = state.get("state_catalog", [])
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    if not draft_scenarios:
        logger.warning(f"[{NODE_NAME}] No draft scenarios to validate.")
        return {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "validated_scenarios": [],
            "low_confidence_scenarios": [],
            "needs_revision_scenarios": [],
            "rejected_scenarios": [],
            "scenario_validation_report": {"summary": {"total": 0}}
        }

    try:
        result = await ScenarioValidationService.run_validation(
            db=db, 
            run_id=run_id, 
            draft_scenarios=draft_scenarios,
            state_catalog=state_catalog
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Validation failed: {result['error']}")
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
            "validated_scenarios": result["validated_scenarios"],
            "low_confidence_scenarios": result["low_confidence_scenarios"],
            "needs_revision_scenarios": result["needs_revision_scenarios"],
            "rejected_scenarios": result["rejected_scenarios"],
            "scenario_validation_report": result["report"],
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
