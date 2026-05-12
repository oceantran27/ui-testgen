"""
LangGraph node for UI Flow Discovery (Agent 3).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.llm_flow_discovery_service import run_ui_flow_discovery
from app.services.graph_progress import persist_run_graph_progress

async def llm_flow_discovery_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    await persist_run_graph_progress(run_id, "llm_flow_discovery_node")
    
    canonical_state_set = state.get("canonical_state_set")
    if not canonical_state_set:
        # Fallback for transition compatibility
        canonical_state_set = {"canonical_states": state.get("canonical_state_catalog", [])}

    result = await run_ui_flow_discovery(
        db=db,
        run_id=run_id,
        canonical_state_set=canonical_state_set
    )

    return {
        "flow_discovery_result": result,
        "flow_clusters": result.get("flows", []),
        "unassigned_state_ids": result.get("unassigned_state_ids", []),
        "current_node": "llm_flow_discovery_node",
        "completed_nodes": ["llm_flow_discovery_node"],
    }
