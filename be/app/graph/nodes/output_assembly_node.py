"""
LangGraph node for Research Output Assembly.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.research_output_assembly_service import run_research_output_assembly
from app.core.pipeline_run_log import is_active, log_node, log_node_return
from app.services.graph_progress import persist_run_graph_progress

async def output_assembly_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    await persist_run_graph_progress(run_id, "output_assembly_node")

    if is_active():
        log_node(
            "output_assembly_node",
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
        "current_node": "output_assembly_node"
    }
    if is_active():
        log_node_return("output_assembly_node", ["ok"], out)
    return out
