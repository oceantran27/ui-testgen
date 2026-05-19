"""
LangGraph node: one batched text LLM call for global flow composition over compressed_catalog.
"""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.graph.state.graph_state import PipelineState
from app.services.global_flow_discovery_service import run_global_flow_discovery
from app.services.graph_progress import persist_run_graph_progress



async def global_flow_discovery_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "global_flow_discovery_node"
    await persist_run_graph_progress(run_id, node_name)

    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Compose behaviour flow candidates from compressed UI behaviour cards "
                "(cross-screen visible alignment, action-result compatibility, outcome branching, uncertainty).",
                "routing: generate_tests_node unless pipeline stopped.",
            ],
            state_keys=("run_id", "compressed_catalog_package"),
            state=state,
        )

    cmp_pkg = state.get("compressed_catalog_package") or {}
    if not cmp_pkg.get("compressed_catalog"):
        return {
            "should_stop": True,
            "stop_reason": "NO_COMPRESSED_CATALOG",
            "graph_status": "failed",
            "current_node": node_name,
        }

    result = await run_global_flow_discovery(db, run_id, compressed_catalog_package=cmp_pkg)

    rep = result.get("report") or {}
    nested_metrics = dict(rep.get("metrics") or {})
    out: Dict[str, Any] = {
        "flow_discovery_result": result,
        "warnings": list(result.get("discovery_warnings") or []),
        "current_node": node_name,
        "completed_nodes": [node_name],
        "metrics": {
            **nested_metrics,
            "global_flow_discovery_input_catalog_char_len": rep.get("global_discovery_input_catalog_char_len"),
        },
    }

    if rep.get("pipeline_stop_after_discovery"):
        out["should_stop"] = True
        out["stop_reason"] = str(rep.get("failure_type") or "GLOBAL_FLOW_DISCOVERY_FAILED")
        out["graph_status"] = "failed"
    elif not result.get("candidate_flows"):
        out["should_stop"] = True
        out["stop_reason"] = "NO_DISCOVERED_FLOWS_AFTER_REPAIR"
        out["graph_status"] = "failed"

    if is_active():
        log_node_return(node_name, ["ok"], out)
    return out
