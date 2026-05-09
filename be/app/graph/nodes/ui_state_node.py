"""
UI State Extraction Node — LangGraph node for Phase 6.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.ui_state_service import run_ui_state_extraction

NODE_NAME = "ui_state_extraction"

async def ui_state_extraction_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 6 — UI State Understanding.
    Receives state with canonical_images.
    Returns updated state with state_catalog and ui_state_extraction_report.
    """
    run_id = state["run_id"]
    canonical_images = state.get("canonical_images", [])
    
    if not canonical_images:
        logger.warning(f"[{NODE_NAME}] No canonical images for run {run_id}. Skipping.")
        return {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "should_stop": True,
            "stop_reason": "NO_CANONICAL_IMAGES",
            "graph_status": "failed"
        }
        
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await run_ui_state_extraction(db=db, run_id=run_id, canonical_images=canonical_images)

        updates: Dict[str, Any] = {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "state_catalog": result["state_catalog"],
            "ui_state_extraction_report": result["report"],
            "metrics": {
                f"{NODE_NAME}_extracted_count": len(result["state_catalog"]),
                f"{NODE_NAME}_failed_count": result["report"].get("failed_extractions_count", 0),
            }
        }

        # Route to failure if no states were successfully extracted
        if not result["state_catalog"]:
             updates["should_stop"] = True
             updates["stop_reason"] = "NO_UI_STATES_EXTRACTED"
             updates["graph_status"] = "failed"
             updates["errors"] = [f"[{NODE_NAME}] All canonical images failed UI extraction"]

        return updates

    except Exception as e:
        logger.exception(f"[{NODE_NAME}] Unexpected error for run {run_id}: {e}")
        return {
            "current_node": NODE_NAME,
            "failed_nodes": [NODE_NAME],
            "errors": [str(e)],
            "should_stop": True,
            "stop_reason": f"NODE_ERROR: {e}",
            "graph_status": "failed"
        }
