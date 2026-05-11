"""
LangGraph node for Semantic Duplicate Adjudication.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.semantic_duplicate_service import run_semantic_duplicate_adjudication
from app.core.pipeline_run_log import is_active, log_node, log_node_return

async def semantic_duplicate_adjudication_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    state_catalog = state.get("state_catalog", [])

    if is_active():
        log_node(
            "semantic_duplicate_adjudication_node",
            intent_lines=[
                "LLM/text merge of near-duplicate states → canonical_state_catalog.",
                "routing: llm_flow_discovery unless should_stop.",
            ],
            state_keys=("run_id", "state_catalog", "should_stop", "ui_state_extraction_report"),
            state=state,
        )

    result = await run_semantic_duplicate_adjudication(db, run_id, state_catalog)

    out = {
        "semantic_duplicate_groups": result["semantic_duplicate_groups"],
        "canonical_state_catalog": result["canonical_state_catalog"],
        "semantic_duplicate_report": result["report"],
        "current_node": "semantic_duplicate_adjudication_node"
    }
    if is_active():
        log_node_return("semantic_duplicate_adjudication_node", ["ok"], out)
    return out
