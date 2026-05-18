"""
LangGraph node: assemble final_output.json from PipelineState.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.pipeline_output_assembly_service import run_pipeline_output_assembly
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def output_assembly_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    node_name = "output_assembly_node"
    await persist_run_graph_progress(run_id, node_name)

    if is_active():
        log_node(
            node_name,
            intent_lines=[
                "Assemble final_output.json + metrics from graph state.",
                "routing: graph_finalizer always next.",
            ],
            state_keys=(
                "run_id",
                "validated_scenario_package",
                "scenario_draft_package",
                "final_output",
                "should_stop",
            ),
            state=state,
        )

    final_output = await run_pipeline_output_assembly(db, run_id, state)

    out = {
        "final_output": final_output,
        "metrics": final_output.get("metrics", {}),
        "current_node": node_name,
        "completed_nodes": [node_name],
    }
    if is_active():
        log_node_return(node_name, ["ok"], out)
    return out
