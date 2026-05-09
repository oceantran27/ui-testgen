"""
Image Preprocessing Node — LangGraph node that runs Module 2 pipeline.

This node:
  1. Reads run_id from state.
  2. Calls preprocessing_service.run_preprocessing() (all validation + normalize + thumbnail).
  3. Writes results back into PipelineState.
  4. Sets should_stop=True if no valid images remain.
"""
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger, log_event
from app.graph.state.graph_state import PipelineState
from app.services.preprocessing_service import run_preprocessing


NODE_NAME = "image_preprocessing"


async def image_preprocessing_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    LangGraph node for Phase 2 — Image Preprocessing.

    Receives state with at least: run_id
    Returns updated state with: valid_images, invalid_images,
                                image_quality_report, should_stop
    """
    run_id = state["run_id"]
    log_event("image_preprocessing_node_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await run_preprocessing(db=db, run_id=run_id)

        # Return partial state update for reducers
        updates: Dict[str, Any] = {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "valid_images": result["valid_images"],
            "invalid_images": result["invalid_images"],
            "image_quality_report": result["report"],
            "preprocessing_warnings": _collect_warnings(result["valid_images"]),
            "metrics": {f"{NODE_NAME}_valid_count": result["valid_count"]}
        }
        
        if result.get("errors"):
            updates["errors"] = result["errors"]

        # Conditional: halt pipeline if no valid images
        if result["valid_count"] == 0:
            updates["should_stop"] = True
            updates["stop_reason"] = "NO_VALID_IMAGES"
            updates["graph_status"] = "failed"
            log_event("pipeline_halted", run_id=run_id, node_name=NODE_NAME,
                      error_code="NO_VALID_IMAGES")
        else:
            updates["should_stop"] = False
            updates["stop_reason"] = None

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



def _collect_warnings(valid_images: list) -> list:
    """Flatten per-image warnings into a single list."""
    all_warnings = []
    for img in valid_images:
        for w in img.get("warnings", []):
            all_warnings.append(f"[{img['image_id']}] {w}")
    return all_warnings
