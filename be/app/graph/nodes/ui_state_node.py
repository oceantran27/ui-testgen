"""
LangGraph node for UI State Extraction (Agent 1).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.ui_state_service import run_ui_state_extraction
from app.services.graph_progress import persist_run_graph_progress

async def ui_state_extraction_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    await persist_run_graph_progress(run_id, "ui_state_extraction_node")
    
    canonical_images = state.get("exact_canonical_images", [])
    if not canonical_images:
        return {
            "should_stop": True,
            "stop_reason": "NO_CANONICAL_IMAGES",
            "current_node": "ui_state_extraction_node"
        }

    result = await run_ui_state_extraction(db=db, run_id=run_id, canonical_images=canonical_images)

    return {
        "ui_state_package": result,
        "state_catalog": result.get("extracted_states", []),
        "current_node": "ui_state_extraction_node",
        "completed_nodes": ["ui_state_extraction_node"],
    }
