"""
UI Flow Discovery Service — Agent 3.
Discovers user behavior flows using structured LLM reasoning.
"""
import json
import time
import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.flow import Flow
from app.db.models.flow_transition import FlowTransition
from app.model_providers import model_adapter
from app.model_providers.schemas import UIFlowDiscoveryResult
from app.core.prompt_manager import prompt_manager


def _generate_flow_id() -> str:
    return f"fl_{uuid.uuid4().hex[:12]}"

def _generate_transition_id() -> str:
    return f"tr_{uuid.uuid4().hex[:12]}"


async def run_ui_flow_discovery(
    db: AsyncSession, 
    run_id: str, 
    canonical_state_set: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Groups canonical states into behavior flows and infers transitions.
    """
    start_time = time.time()
    log_event("ui_flow_discovery_started", run_id=run_id)

    canonical_states = canonical_state_set.get("canonical_states", [])
    if not canonical_states:
        return UIFlowDiscoveryResult(
            flow_discovery_result_id="",
            source_canonical_state_set_id=canonical_state_set.get("canonical_state_set_id", ""),
            flows=[],
            unassigned_state_ids=[],
            discovery_warnings=["NO_CANONICAL_STATES"],
        ).model_dump()

    system_instruction = prompt_manager.get_prompt("llm_flow_discovery")

    user_instruction = (
        f"Group the following {len(canonical_states)} canonical UI states into behaviour flows "
        f"and infer ordered transitions:\n"
        f"{json.dumps(canonical_states, indent=2)}\n"
    )

    response = await model_adapter.call_text_structured(
        task_name="ui_flow_discovery",
        run_id=run_id,
        node_name="llm_flow_discovery_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=UIFlowDiscoveryResult,
        prompt_name="llm_flow_discovery_prompt",
        prompt_version="v1",
        provider_override=settings.LLM_FLOW_DISCOVERY_MODEL_PROVIDER,
        model_name_override=settings.LLM_FLOW_DISCOVERY_MODEL_NAME,
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"UI Flow Discovery failed: {response.error}")
        err = UIFlowDiscoveryResult(
            flow_discovery_result_id="",
            source_canonical_state_set_id=canonical_state_set.get("canonical_state_set_id", ""),
            flows=[],
            unassigned_state_ids=[],
            discovery_warnings=[str(response.error or "LLM_FAILED")],
        ).model_dump()
        err["report"] = {"error": str(response.error)}
        return err

    result: UIFlowDiscoveryResult = response.parsed_output

    for flow_data in result.flows:
        # Save Flow to DB
        flow_row = Flow(
            id=flow_data.flow_id,
            run_id=run_id,
            name=flow_data.flow_label,
            flow_type=flow_data.flow_type,
            flow_label=flow_data.flow_label,
            input_level="AGENT_3_FLOW_DISCOVERY",
            entry_state_id=flow_data.entry_state_id,
            ordered_state_ids_json={"ids": flow_data.state_ids},
            terminal_state_ids_json={"ids": flow_data.terminal_state_ids},
            flow_completeness_json=flow_data.flow_completeness.model_dump(),
            confidence=0.0, # Placeholder
        )
        db.add(flow_row)
        
        # Save Transitions
        for tr_data in flow_data.transitions:
            tr_row = FlowTransition(
                id=tr_data.transition_id,
                run_id=run_id,
                flow_id=flow_data.flow_id,
                from_state_id=tr_data.from_state_id,
                to_state_id=tr_data.to_state_id,
                transition_type="llm_inferred",
                trigger_element_id=tr_data.trigger_element_id,
                transition_basis=tr_data.transition_basis,
                ordering_strength=tr_data.ordering_strength,
                supporting_evidence_refs_json={"refs": [r.model_dump() for r in tr_data.supporting_evidence_refs]},
                uncertainty_reason=tr_data.uncertainty_reason,
            )
            db.add(tr_row)

    await db.commit()

    report = {
        "discovered_flow_count": len(result.flows),
        "unassigned_state_count": len(result.unassigned_state_ids),
        "warnings": result.discovery_warnings,
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("ui_flow_discovery_completed", run_id=run_id, duration_ms=duration_ms)

    return result.model_dump()
