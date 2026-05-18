"""
LangGraph node for Scenario Evidence Audit (Agent 7).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.scenario_evidence_audit_service import (
    run_scenario_evidence_audit,
    revision_hints_from_validated_package,
)
from app.core.logging import logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def scenario_evidence_audit_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "scenario_evidence_audit_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Audit generated test scenarios against UI evidence and screen intents.",
            ],
            state_keys=("run_id",),
            state=state
        )
    
    scenario_draft_package = state.get("scenario_draft_package", {})
    if not scenario_draft_package:
        return {
            "should_stop": True,
            "stop_reason": "NO_SCENARIO_DRAFTS",
            "graph_status": "failed",
            "audit_revision_suggestions": [],
        }
    

    flow_discovery_result = state.get("flow_discovery_result", {})
    intent_package = state.get("intent_package", {})
    screen_intent_package = state.get("screen_intent_package", {})
    state_catalog = state.get("state_catalog") or []
    compressed_catalog_package = state.get("compressed_catalog_package") or {}

    result = await run_scenario_evidence_audit(
        db=db,
        run_id=run_id,
        scenario_draft_package=scenario_draft_package,

        flow_discovery_result=flow_discovery_result,
        intent_package=intent_package,
        screen_intent_package=screen_intent_package,
        state_catalog=state_catalog,
        compressed_catalog_package=compressed_catalog_package,
    )

    hints = revision_hints_from_validated_package(result)
    out = {
        "validated_scenario_package": result,
        "audit_revision_suggestions": hints,
        "current_node": node_name,
        "completed_nodes": [node_name],
    }
    if is_active():
        log_node_return(node_name, ["ok"], out)
    return out
