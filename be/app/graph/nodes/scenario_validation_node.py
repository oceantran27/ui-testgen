"""
Scenario Grounding & Validation Node — LangGraph node for Phase 12.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.scenario_validation_service import ScenarioValidationService
from app.core.pipeline_run_log import is_active, log_node, log_node_return, console_err, console_warn

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
    flow_clusters = state.get("flow_clusters", [])
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    if is_active():
        log_node(
            NODE_NAME,
            intent_lines=[
                "LLM-as-judge validation for draft scenarios.",
                "routing: output_assembly unless should_stop.",
            ],
            state_keys=("run_id", "draft_scenarios", "state_catalog", "flow_clusters", "should_stop"),
            state=state,
        )

    if not draft_scenarios:
        logger.warning(f"[{NODE_NAME}] No draft scenarios to validate.")
        if is_active():
            console_warn(f"{NODE_NAME}: nothing to validate")
        out = {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "validated_scenarios": [],
            "low_confidence_scenarios": [],
            "needs_revision_scenarios": [],
            "rejected_scenarios": [],
            "scenario_validation_report": {"summary": {"total": 0}}
        }
        if is_active():
            log_node_return(NODE_NAME, ["empty draft_scenarios"], out)
        return out

    try:
        result = await ScenarioValidationService.run_validation(
            db=db, 
            run_id=run_id, 
            draft_scenarios=draft_scenarios,
            state_catalog=state_catalog,
            flow_clusters=flow_clusters
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Validation failed: {result['error']}")
            fail = {
                "current_node": NODE_NAME,
                "failed_nodes": [NODE_NAME],
                "errors": [result["error"]],
                "should_stop": True,
                "graph_status": "failed"
            }
            if is_active():
                console_err(f"{NODE_NAME}: {result['error']}")
                log_node_return(NODE_NAME, ["service error"], fail)
            return fail

        updates: Dict[str, Any] = {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "validated_scenarios": result["validated_scenarios"],
            "low_confidence_scenarios": result["low_confidence_scenarios"],
            "needs_revision_scenarios": result["needs_revision_scenarios"],
            "rejected_scenarios": result["rejected_scenarios"],
            "scenario_validation_report": result["report"],
        }

        if is_active():
            log_node_return(NODE_NAME, ["ok"], updates)
        return updates

    except Exception as e:
        logger.exception(f"[{NODE_NAME}] Unexpected error for run {run_id}: {e}")
        if is_active():
            console_err(f"{NODE_NAME}: {e}")
        fail = {
            "current_node": NODE_NAME,
            "failed_nodes": [NODE_NAME],
            "errors": [str(e)],
            "should_stop": True,
            "graph_status": "failed"
        }
        if is_active():
            log_node_return(NODE_NAME, ["exception"], fail)
        return fail
