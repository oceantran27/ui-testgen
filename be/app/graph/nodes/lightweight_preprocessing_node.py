"""
LangGraph node for Lightweight Preprocessing.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.lightweight_preprocessing_service import run_lightweight_preprocessing
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def lightweight_preprocessing_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    await persist_run_graph_progress(run_id, "lightweight_preprocessing_node")
    image_ids = state["raw_image_ids"]

    if is_active():
        log_node(
            "lightweight_preprocessing_node",
            intent_lines=[
                "Mark images valid; ensure normalized_uri falls back to storage_uri.",
                "routing: exact_duplicate unless should_stop from earlier.",
            ],
            state_keys=("run_id", "raw_image_ids", "config", "should_stop"),
            state=state,
        )

    result = await run_lightweight_preprocessing(db, run_id, image_ids)

    out = {
        "valid_images": result["valid_images"],
        "image_quality_report": result["report"],
        "preprocessing_warnings": result["warnings"],
        "current_node": "lightweight_preprocessing_node"
    }
    if is_active():
        log_node_return("lightweight_preprocessing_node", ["ok"], out)
    return out
