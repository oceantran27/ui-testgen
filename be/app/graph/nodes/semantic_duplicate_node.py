"""
LangGraph node for Semantic Canonicalization (Agent 2).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.semantic_duplicate_service import run_semantic_canonicalization
from app.services.graph_progress import persist_run_graph_progress

async def semantic_duplicate_adjudication_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    await persist_run_graph_progress(run_id, "semantic_duplicate_adjudication_node")
    
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
        "current_node": "semantic_duplicate_adjudication_node",
        "completed_nodes": ["semantic_duplicate_adjudication_node"],
    }
