"""Update `Run.current_node` / `progress_percentage` for UI polling (separate DB session)."""
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.db.models.run import Run

# Must match `fe/src/constants/pipeline.ts` and LangGraph `graph_runner.py` order
PIPELINE_NODE_ORDER = [
    "init_run_context_node",
    "ui_state_evidence_extraction_node",
    "screen_intent_extraction_v2_node",
    "flow_context_builder_node",
    "intent_aware_flow_discovery_node",
    "behaviour_contract_builder_node",
    "behaviour_scenario_generation_node",
    "scenario_evidence_audit_node",
    "output_assembly_node",
    "graph_finalizer_node",
]


# LangGraph state sometimes uses short `NODE_NAME`; DB/UI expect *_node ids.
_PIPELINE_NODE_ALIASES: dict[str, str] = {
    "ui_state_evidence_extraction": "ui_state_evidence_extraction_node",
    "screen_intent_extraction_v2": "screen_intent_extraction_v2_node",
    "flow_context_builder": "flow_context_builder_node",
    "intent_aware_flow_discovery": "intent_aware_flow_discovery_node",
    "behaviour_contract_builder": "behaviour_contract_builder_node",
    "behaviour_scenario_generation": "behaviour_scenario_generation_node",
    "scenario_evidence_audit": "scenario_evidence_audit_node",
}


async def persist_run_graph_progress(run_id: str, node_name: str) -> None:
    canonical = _PIPELINE_NODE_ALIASES.get(node_name, node_name)
    try:
        idx = PIPELINE_NODE_ORDER.index(canonical)
    except ValueError:
        return
    n = len(PIPELINE_NODE_ORDER)
    pct = min(99, max(1, int((idx + 1) / n * 100)))
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if run:
            run.current_node = canonical
            run.progress_percentage = pct
            await db.commit()
