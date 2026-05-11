"""
LangGraph node for Exact Duplicate Detection.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.exact_duplicate_service import run_exact_duplicate_detection
from app.core.pipeline_run_log import is_active, log_node, log_node_return

async def exact_duplicate_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    # We only process valid images from preprocessing
    image_ids = [img["image_id"] for img in state.get("valid_images", [])]

    if is_active():
        log_node(
            "exact_duplicate_node",
            intent_lines=[
                "pHash/dHash grouping; choose canonicals per group.",
                "routing: ui_state_extraction unless should_stop.",
            ],
            state_keys=("run_id", "valid_images", "should_stop", "image_quality_report"),
            state=state,
        )

    result = await run_exact_duplicate_detection(db, run_id, image_ids)

    out = {
        "exact_duplicate_groups": result["exact_duplicate_groups"],
        "exact_canonical_images": result["exact_canonical_images"],
        "exact_duplicate_report": result["report"],
        "current_node": "exact_duplicate_node"
    }
    if is_active():
        log_node_return("exact_duplicate_node", ["ok"], out)
    return out
