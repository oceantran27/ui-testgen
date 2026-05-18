"""Update `Run.current_node` / `progress_percentage` for UI polling (separate DB session)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models.run import Run

# Separated pipeline (legacy baseline): Agent 1 vision → Agent 2 text → compression …
PIPELINE_NODE_ORDER_SEPARATED = [
    "init_run_context_node",
    "ui_state_evidence_extraction_node",
    "screen_intent_extraction_v2_node",
    "representation_compression_node",
    "global_flow_discovery_node",
    "generate_tests_node",
    "scenario_evidence_audit_node",
    "output_assembly_node",
    "graph_finalizer_node",
]

# Joint pipeline: single vision pass per image replaces A1+A2 screen-local calls
PIPELINE_NODE_ORDER_JOINT = [
    "init_run_context_node",
    "joint_screen_understanding_node",
    "representation_compression_node",
    "global_flow_discovery_node",
    "generate_tests_node",
    "scenario_evidence_audit_node",
    "output_assembly_node",
    "graph_finalizer_node",
]


async def resolve_screen_understanding_mode(db: AsyncSession, run_id: str) -> str:
    """``run.config_json['screen_understanding_mode']`` overrides ``settings.SCREEN_UNDERSTANDING_MODE``."""
    result = await db.execute(select(Run).where(Run.id == run_id))
    run = result.scalar_one_or_none()
    mode = settings.SCREEN_UNDERSTANDING_MODE
    if run and run.config_json:
        cfg_mode = run.config_json.get("screen_understanding_mode")
        if cfg_mode in ("joint", "separated"):
            mode = cfg_mode
    return mode


# Must match `fe/src/constants/pipeline.ts` for the active mode (joint vs separated)
_PIPELINE_NODE_ALIASES: dict[str, str] = {
    "ui_state_evidence_extraction": "ui_state_evidence_extraction_node",
    "screen_intent_extraction_v2": "screen_intent_extraction_v2_node",
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
        mode = await resolve_screen_understanding_mode(db, run_id)
        pipeline_order = PIPELINE_NODE_ORDER_JOINT if mode == "joint" else PIPELINE_NODE_ORDER_SEPARATED
        try:
            idx = pipeline_order.index(canonical)
        except ValueError:
            return
        n = len(pipeline_order)
        pct = min(99, max(1, int((idx + 1) / n * 100)))
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if run:
            run.current_node = canonical
            run.progress_percentage = pct
            await db.commit()
