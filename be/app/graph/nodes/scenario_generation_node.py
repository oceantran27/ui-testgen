"""
Behaviour Scenario Generation Node — LangGraph node for Phase 11.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.scenario_generation_service import ScenarioGenerationService
from app.core.pipeline_run_log import is_active, log_node, log_node_return, console_err, console_warn

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
    flow_clusters = state.get("flow_clusters", [])
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    if is_active():
        log_node(
            NODE_NAME,
            intent_lines=[
                "Draft Gherkin per BehaviourIntent via LLM.",
                "routing: scenario_validation unless should_stop.",
            ],
            state_keys=("run_id", "behaviour_intents", "state_catalog", "flow_clusters", "should_stop"),
            state=state,
        )

    try:
        result = await ScenarioGenerationService.run_generation(
            db=db, 
            run_id=run_id, 
            behaviour_intents=behaviour_intents,
            state_catalog=state_catalog,
            flow_clusters=flow_clusters
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Generation failed: {result['error']}")
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
            "draft_scenarios": result["draft_scenarios"],
            "scenario_generation_report": result["report"],
        }

        if not result["draft_scenarios"]:
            logger.warning(f"[{NODE_NAME}] No scenarios were generated.")
            if is_active():
                console_warn(f"{NODE_NAME}: no draft scenarios")

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
