"""
Duplicate Detection Node — LangGraph node for Phase 3.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.duplicate_service import run_duplicate_detection

NODE_NAME = "duplicate_detection"

async def duplicate_detection_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 3 — Duplicate Detection.
    Receives state with run_id.
    Returns updated state with canonical_images, duplicate_groups, duplicate_detection_report.
    """
    run_id = state["run_id"]
    log_event("duplicate_detection_node_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await run_duplicate_detection(db=db, run_id=run_id)

        updates: Dict[str, Any] = {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "duplicate_groups": result["duplicate_groups"],
            "canonical_images": result["canonical_images"],
            "duplicate_detection_report": result["report"],
            "metrics": {
                f"{NODE_NAME}_canonical_count": len(result["canonical_images"]),
                f"{NODE_NAME}_group_count": len(result["duplicate_groups"]),
            }
        }

        # If no canonical images (highly unlikely if there were valid images), halt
        if not result["canonical_images"] and state.get("valid_images"):
             updates["should_stop"] = True
             updates["stop_reason"] = "NO_CANONICAL_IMAGES"
             updates["graph_status"] = "failed"

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

