"""Update `Run.current_node` / `progress_percentage` for UI polling (separate DB session)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.models.run import Run

PIPELINE_NODE_ORDER = [
    "init_run_context_node",
    "joint_screen_understanding_node",
    "representation_compression_node",
    "global_flow_discovery_node",
    "generate_tests_node",
    "scenario_evidence_audit_node",
    "output_assembly_node",
    "graph_finalizer_node",
]

# Backend agent / legacy aliases → canonical LangGraph node id
_PIPELINE_NODE_ALIASES: dict[str, str] = {
    "joint_screen_understanding": "joint_screen_understanding_node",
    "compressed_representation": "representation_compression_node",
    "representation_compression": "representation_compression_node",
    "global_flow_discovery": "global_flow_discovery_node",
    "flow_context_builder": "global_flow_discovery_node",
    "transition_evidence": "global_flow_discovery_node",
    "intent_aware_flow_discovery": "global_flow_discovery_node",
    "discover_flows": "global_flow_discovery_node",
    "behaviour_contract_builder": "generate_tests_node",
    "behaviour_scenario_generation": "generate_tests_node",
    "generate_tests": "generate_tests_node",
    "scenario_evidence_audit": "scenario_evidence_audit_node",
}


async def persist_run_graph_progress(run_id: str, node_name: str) -> None:
    canonical = _PIPELINE_NODE_ALIASES.get(node_name, node_name)
    async with AsyncSessionLocal() as db:
        try:
            idx = PIPELINE_NODE_ORDER.index(canonical)
        except ValueError:
            return
        n = len(PIPELINE_NODE_ORDER)
        pct = min(99, max(1, int((idx + 1) / n * 100)))
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if run:
            run.current_node = canonical
            run.progress_percentage = pct
            await db.commit()
