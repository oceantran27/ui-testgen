"""
LangGraph node: deterministic compression of UI state + screen intents for batched global discovery.
"""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.graph.state.graph_state import PipelineState
from app.services.compressed_representation_service import (
    run_build_compressed_catalog,
    validate_compressed_catalog_size,
)
from app.services.graph_progress import persist_run_graph_progress


async def representation_compression_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "representation_compression_node"
    await persist_run_graph_progress(run_id, node_name)

    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Compress Phase1+2 artefacts into token-light catalog for global flow discovery.",
                "routing: global_flow_discovery_node unless pipeline stopped.",
            ],
            state_keys=("run_id", "state_catalog", "screen_intent_package"),
            state=state,
        )

    state_catalog = state.get("state_catalog") or []
    sip = state.get("screen_intent_package") or {}

    if not state_catalog:
        return {
            "should_stop": True,
            "stop_reason": "NO_STATE_CATALOG",
            "graph_status": "failed",
            "current_node": node_name,
        }

    try:
        pkg = run_build_compressed_catalog(
            run_id=run_id,
            state_catalog=state_catalog,
            screen_intent_pkg=sip,
            ui_state_package=state.get("ui_state_package"),
        )
        ok, err = validate_compressed_catalog_size(pkg, max_screens=settings.GLOBAL_FLOW_DISCOVERY_MAX_SCREENS)
        if not ok:
            return {
                "should_stop": True,
                "stop_reason": err or "COMPRESSED_CATALOG_INVALID",
                "graph_status": "failed",
                "current_node": node_name,
                "compressed_catalog_package": pkg,
                "metrics": {"compression": pkg.get("compression_stats") or {}},
            }

        stats = pkg.get("compression_stats") or {}

        out: Dict[str, Any] = {
            "compressed_catalog_package": pkg,
            "metrics": {
                "compression": stats,
                "compressed_catalog_token_estimate": stats.get("token_estimate_div4"),
            },
            "current_node": node_name,
            "completed_nodes": [node_name],
        }
        if is_active():
            log_node_return(node_name, ["ok"], out)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] Error for run %s: %s", node_name, run_id, exc)
        await db.rollback()
        return {
            "current_node": node_name,
            "failed_nodes": [node_name],
            "errors": [f"{node_name}: {exc}"],
            "should_stop": True,
            "stop_reason": f"CRITICAL_NODE_ERROR: {exc}",
            "graph_status": "failed",
        }
