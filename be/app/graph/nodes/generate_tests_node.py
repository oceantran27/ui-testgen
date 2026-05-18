"""
LangGraph node: Agents 5 + 6 — behaviour contracts then BDD scenario generation.
"""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.graph.state.graph_state import PipelineState
from app.services.generate_tests_service import run_generate_tests
from app.services.graph_progress import persist_run_graph_progress


async def generate_tests_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "generate_tests_node"
    await persist_run_graph_progress(run_id, node_name)

    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Build behaviour contracts, scenario blueprints with mandatory anchors,",
                "LLM scenario writer → keyword validator → persist drafts (pending_audit).",
                "routing: scenario_evidence_audit unless pipeline stopped.",
            ],
            state_keys=("run_id", "flow_discovery_result", "compressed_catalog_package"),
            state=state,
        )

    flow_discovery_result = state.get("flow_discovery_result", {})
    if not flow_discovery_result:
        return {
            "should_stop": True,
            "stop_reason": "NO_FLOW_DISCOVERY_RESULT",
            "graph_status": "failed",
            "current_node": node_name,
        }

    state_catalog = state.get("state_catalog", [])
    compressed_catalog_package = state.get("compressed_catalog_package") or {}
    screen_intent_package = state.get("screen_intent_package") or {}
    intent_pkg, scenario_pkg = await run_generate_tests(
        db=db,
        run_id=run_id,
        flow_discovery_result=flow_discovery_result,
        state_catalog=state_catalog,
        compressed_catalog_package=compressed_catalog_package,
    )

    out: Dict[str, Any] = {
        "intent_package": intent_pkg,
        "scenario_draft_package": scenario_pkg,
        "audit_revision_suggestions": [],
        "current_node": node_name,
        "completed_nodes": [node_name],
    }
    if is_active():
        log_node_return(node_name, ["ok"], out)
    return out
