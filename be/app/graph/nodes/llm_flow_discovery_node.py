"""
LangGraph node for LLM Flow Discovery.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.llm_flow_discovery_service import run_llm_flow_discovery
from app.core.pipeline_run_log import is_active, log_node, log_node_return

async def llm_flow_discovery_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    canonical_state_catalog = state.get("canonical_state_catalog", [])

    if is_active():
        log_node(
            "llm_flow_discovery_node",
            intent_lines=[
                "LLM clusters states into flows + report.",
                "routing: behaviour_intent_inference unless should_stop.",
            ],
            state_keys=("run_id", "canonical_state_catalog", "should_stop"),
            state=state,
        )

    result = await run_llm_flow_discovery(db, run_id, canonical_state_catalog)

    out = {
        "flow_clusters": result["flow_clusters"],
        "unassigned_state_ids": result["unassigned_state_ids"],
        "flow_discovery_report": result["report"],
        "detected_flows": [f["flow_name"] for f in result["flow_clusters"]],
        "current_node": "llm_flow_discovery_node"
    }
    if is_active():
        log_node_return("llm_flow_discovery_node", ["ok"], out)
    return out
