"""
LangGraph node for Research Output Assembly.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.research_output_assembly_service import run_research_output_assembly
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.core.logging import logger
from app.services.graph_progress import persist_run_graph_progress

async def output_assembly_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "output_assembly_node"
    await persist_run_graph_progress(run_id, node_name)

    try:
        if is_active():
            log_node(
                node_name,
                intent_lines=[
                    "Assemble final research JSON + artifacts from graph state.",
                    "routing: graph_finalizer always next.",
                ],
                state_keys=(
                    "run_id",
                    "validated_scenarios",
                    "draft_scenarios",
                    "final_output",
                    "should_stop",
                ),
                state=state,
            )

        final_output = await run_research_output_assembly(db, run_id, state)

        out = {
            "final_output": final_output,
            "metrics": final_output.get("metrics", {}),
            "current_node": node_name
        }
        if is_active():
            log_node_return(node_name, ["ok"], out)
        return out
    except Exception as e:
        logger.exception(f"[{node_name}] Error for run {run_id}: {e}")
        return {
            "current_node": node_name,
            "failed_nodes": [node_name],
            "errors": [f"{node_name}: {e}"],
            "should_stop": True,
            "stop_reason": f"CRITICAL_NODE_ERROR: {e}",
            "graph_status": "failed"
        }
