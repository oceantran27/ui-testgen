"""
LangGraph node for Semantic Canonicalization (Agent 2).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.semantic_duplicate_service import run_semantic_canonicalization
from app.core.logging import log_event, logger
from app.services.graph_progress import persist_run_graph_progress

async def semantic_duplicate_adjudication_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "semantic_duplicate_adjudication_node"
    await persist_run_graph_progress(run_id, node_name)
    
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

        return {
            "canonical_state_set": result,
            "canonical_state_catalog": result.get("canonical_states", []),
            "current_node": node_name,
            "completed_nodes": [node_name],
        }
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
