"""
LangGraph node: joint vision extraction — UI evidence + local screen intents per image.
"""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.graph.state.graph_state import PipelineState
from app.services.graph_progress import persist_run_graph_progress
from app.services.joint_screen_understanding_service import run_joint_screen_understanding


async def joint_screen_understanding_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "joint_screen_understanding_node"
    await persist_run_graph_progress(run_id, node_name)

    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Joint vision: UI state evidence + interaction groups + local behaviour intents per screenshot.",
            ],
            state_keys=("run_id", "raw_image_ids"),
            state=state,
        )

    try:
        image_ids = state.get("raw_image_ids", [])
        if not image_ids:
            return {
                "should_stop": True,
                "stop_reason": "NO_IMAGE_IDS",
                "graph_status": "failed",
            }

        result = await run_joint_screen_understanding(db=db, run_id=run_id, image_ids=image_ids)

        out: Dict[str, Any] = {
            "ui_state_package": result["ui_state_package"],
            "state_catalog": result["state_catalog"],
            "interaction_group_catalog": result["interaction_group_catalog"],
            "screen_intent_package": result["screen_intent_package"],
            "metrics": result.get("metrics") or {},
            "current_node": node_name,
            "completed_nodes": [node_name],
        }
        if is_active():
            log_node_return(node_name, ["ok"], out)
        return out
    except Exception as e:
        logger.exception(f"[{node_name}] Error for run {run_id}: {e}")
        await db.rollback()
        return {
            "current_node": node_name,
            "failed_nodes": [node_name],
            "errors": [f"{node_name}: {e}"],
            "should_stop": True,
            "stop_reason": f"CRITICAL_NODE_ERROR: {e}",
            "graph_status": "failed",
        }

