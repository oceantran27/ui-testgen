"""
UI State Extraction Node — LangGraph node for Phase 6.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.ui_state_service import run_ui_state_extraction
from app.core.pipeline_run_log import is_active, log_node, log_node_return, console_err, console_warn

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
    canonical_images = state.get("exact_canonical_images", [])
    
    if not canonical_images:
        logger.warning(f"[{NODE_NAME}] No canonical images for run {run_id}. Skipping.")
        if is_active():
            console_warn("ui_state_extraction: no canonical images")
        out = {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "should_stop": True,
            "stop_reason": "NO_CANONICAL_IMAGES",
            "graph_status": "failed"
        }
        if is_active():
            log_node_return("ui_state_extraction", ["no canonical images"], out)
        return out
        
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    if is_active():
        log_node(
            "ui_state_extraction",
            intent_lines=[
                "VLM per canonical image → state_catalog + DB UIState/UIElement.",
                "routing: semantic_duplicate_adjudication unless should_stop.",
            ],
            state_keys=("run_id", "exact_canonical_images", "valid_images", "should_stop"),
            state=state,
        )

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

        if is_active():
            log_node_return("ui_state_extraction", ["done"], updates)
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
            "stop_reason": f"NODE_ERROR: {e}",
            "graph_status": "failed"
        }
        if is_active():
            log_node_return("ui_state_extraction", ["exception"], fail)
        return fail
