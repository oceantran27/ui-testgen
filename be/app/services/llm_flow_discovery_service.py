"""
LLM Flow Discovery Service — Phase Research v1.
Discovers user behavior flows using structured LLM reasoning.
"""
import json
import time
import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.flow import Flow
from app.model_providers import model_adapter
from app.model_providers.schemas import LLMFlowDiscoveryOutput


def _generate_flow_id() -> str:
    return f"fl_{uuid.uuid4().hex[:12]}"


def _llm_flow_type_to_db(flow_type: str) -> str:
    if flow_type == "single_state_inferred_flow":
        return "single_state_pseudo_flow"
    return "linear_flow"


def _confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


async def run_llm_flow_discovery(
    db: AsyncSession, 
    run_id: str, 
    canonical_state_catalog: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Groups canonical states into behavior flows and infers transitions.
    """
    start_time = time.time()
    log_event("llm_flow_discovery_started", run_id=run_id)

    if not canonical_state_catalog:
        return {
            "flow_clusters": [],
            "unassigned_state_ids": [],
            "report": {"reason": "NO_CANONICAL_STATES"}
        }

    system_instruction = (
        "You are a Senior QA Flow Reasoning Agent. Your task is to discover possible user behavior flows "
        "from unordered UI states extracted from screenshots.\n\n"
        "Rules:\n"
        "- Use only the provided UI states and visible evidence.\n"
        "- Do not assume backend data or business rules not visible in the states.\n"
        "- A flow is a sequence of UI states that can plausibly represent a user action and an observable UI result.\n"
        "- If the order is uncertain, mark uncertain_order.\n"
        "- If a final observable result is missing, mark missing_final_verification.\n"
        "- If only one state can be used, create a single_state_inferred_flow.\n"
        "- Every transition must cite evidence_state_ids and evidence_element_ids when available.\n"
    )

    user_instruction = (
        f"Group the following {len(canonical_state_catalog)} canonical UI states into behaviour flows "
        f"and infer ordered transitions:\n"
        f"{json.dumps(canonical_state_catalog, indent=2)}\n"
    )

    response = await model_adapter.call_text_structured(
        task_name="llm_flow_discovery",
        run_id=run_id,
        node_name="llm_flow_discovery_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=LLMFlowDiscoveryOutput,
        prompt_name="llm_flow_discovery_prompt",
        prompt_version="v1",
        provider_override=settings.LLM_FLOW_DISCOVERY_MODEL_PROVIDER,
        model_name_override=settings.LLM_FLOW_DISCOVERY_MODEL_NAME,
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"LLM Flow Discovery failed: {response.error}")
        return {
            "flow_clusters": [],
            "unassigned_state_ids": [s["state_id"] for s in canonical_state_catalog],
            "report": {"error": str(response.error)}
        }

    result: LLMFlowDiscoveryOutput = response.parsed_output

    flow_clusters: List[Dict[str, Any]] = []
    for cluster in result.flows:
        flow_id = _generate_flow_id()
        ordered = list(cluster.ordered_state_ids)
        start_sid = ordered[0] if ordered else None
        conf_label = _confidence_label(cluster.confidence)
        warnings_payload: dict[str, Any] | None = (
            {"llm_warnings": list(cluster.warnings)} if cluster.warnings else None
        )
        flow_row = Flow(
            id=flow_id,
            run_id=run_id,
            name=cluster.flow_name,
            flow_type=_llm_flow_type_to_db(cluster.flow_type),
            input_level="LLM_RESEARCH",
            start_state_id=start_sid,
            ordered_state_ids_json={"ids": ordered},
            completeness_status=cluster.completeness_status,
            confidence=cluster.confidence,
            confidence_label=conf_label,
            warnings_json=warnings_payload,
        )
        db.add(flow_row)
        dumped = cluster.model_dump()
        dumped["flow_id"] = flow_id
        flow_clusters.append(dumped)

    await db.commit()

    report = {
        "input_state_count": len(canonical_state_catalog),
        "discovered_flow_count": len(result.flows),
        "unassigned_state_count": len(result.unassigned_state_ids),
        "warnings": result.global_warnings,
        "persisted_flow_ids": [c["flow_id"] for c in flow_clusters],
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("llm_flow_discovery_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "flow_clusters": flow_clusters,
        "unassigned_state_ids": result.unassigned_state_ids,
        "report": report
    }
