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

_EMPTY_VT = {
    "transition_evidence_package_id": "",
    "verified_edges": [],
    "rejected_edges": [],
    "resolver_metrics": {"engine": "disabled_global_batch"},
    "candidate_edges_before_topk": [],
    "edges_sent_to_vlm": [],
    "vlm_metrics": {"verified_count": 0, "rejected_count": 0, "edge_input_count": 0},
    "warnings": [],
}


async def global_flow_discovery_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "global_flow_discovery_node"
    await persist_run_graph_progress(run_id, node_name)

    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Compose behaviour flow candidates from compressed UI behaviour cards "
                "(semantic continuity, action-result compatibility, outcome branching, uncertainty).",
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

    try:
        result = await run_global_flow_discovery(db, run_id, compressed_catalog_package=cmp_pkg)

        rep = result.get("report") or {}
        nested_metrics = dict(rep.get("metrics") or {})
        out: Dict[str, Any] = {
            "flow_discovery_result": result,
            "flow_context_package": {
                "flow_context_package_id": "",
                "flow_state_cards": [],
                "note": "Legacy flow_state_cards omitted — global_batch path uses compressed_catalog only.",
            },
            "verified_transition_package": _EMPTY_VT,
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
