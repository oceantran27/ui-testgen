"""
LangGraph node for Semantic Canonicalization (Agent 2).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.semantic_duplicate_service import run_semantic_canonicalization
from app.core.logging import log_event, logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def semantic_duplicate_adjudication_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "semantic_duplicate_adjudication_node"
    await persist_run_graph_progress(run_id, node_name)
    
    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Deduplicate UI states semantically.",
                "routing: llm_flow_discovery unless error."
            ],
            state_keys=("run_id", "ui_state_package"),
            state=state
        )
    
    try:
        ui_state_package = state.get("ui_state_package")
        if not ui_state_package:
            catalog = state.get("state_catalog", [])
            ui_state_package = {
                "schema_version": "1.0",
                "ui_state_package_id": "legacy_fallback",
                "extracted_states": catalog,
                "state_catalog": catalog,
            }

        result = await run_semantic_canonicalization(
            db=db,
            run_id=run_id,
            ui_state_package=ui_state_package
        )

        # Prune duplicates: downstream nodes will only see unique states
        unique_states_data = [c["data"] for c in result.get("unique_states", [])]

        out = {
            "canonical_state_set": result,
            "ui_state_package": {
                "extracted_states": unique_states_data,
            },
            "current_node": node_name,
            "completed_nodes": [node_name],
        }
        if is_active():
            log_node_return(node_name, ["ok"], out)
        return out
    except Exception as e:
        logger.exception(f"[{node_name}] Error for run {run_id}: {e}")
        return {
            "current_node": node_name,
            "failed_nodes": [node_name],
            "errors": [f"{node_name}: {e}"],
            "should_stop": True,
            "stop_reason": f"CRITICAL_NODE_ERROR: {e}",
            "graph_status": "failed"
        }
