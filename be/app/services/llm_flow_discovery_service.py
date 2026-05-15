"""
UI Flow Discovery Service — Agent 3.
Discovers user behavior flows using structured LLM reasoning.
"""
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.flow import Flow
from app.db.models.flow_transition import FlowTransition
from app.model_providers import model_adapter
from app.model_providers.schemas import FlowTransitionTriggerA3, UIFlowDiscoveryResult
from app.core.prompt_manager import prompt_manager


def _generate_flow_id(run_id: str) -> str:
    return f"flow_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"

def _generate_transition_id(run_id: str) -> str:
    return f"tr_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


def _hypothesized_action_from_a3_trigger(trigger: FlowTransitionTriggerA3) -> Optional[str]:
    """Human-readable action for DB row; schema uses text list from A3 prompt."""
    if trigger.text:
        return " ".join(trigger.text).strip() or None
    if trigger.action_type:
        return trigger.action_type.strip() or None
    return None



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

    unique_states_raw = (
        canonical_state_set.get("unique_states") 
        or canonical_state_set.get("extracted_states") 
        or []
    )
    if not unique_states_raw:
        return UIFlowDiscoveryResult(
            flow_discovery_result_id=f"fdr_{run_id[-6:]}_{uuid.uuid4().hex[:8]}",
            source_canonical_state_set_id=canonical_state_set.get("ui_state_package_id") or canonical_state_set.get("canonical_state_set_id", "unknown_set"),
            candidate_flows=[],
            semantic_clusters=[],
            uncertain_relations=[],
            discovery_warnings=["NO_UNIQUE_STATES"],
        ).model_dump()

    # Normalization: ensure states are flat (handle A2 nested output)
    unique_states = []
    for s in unique_states_raw:
        if isinstance(s, dict) and "data" in s and isinstance(s["data"], dict):
            # A2 nested format: { "canonical_id": ..., "data": { ... } }
            flat = s["data"].copy()
            if "canonical_id" in s:
                flat["canonical_id"] = s["canonical_id"]
            unique_states.append(flat)
        else:
            # A1 flat format or unknown
            unique_states.append(s)

    system_instruction = prompt_manager.get_prompt("llm_flow_discovery")

    user_instruction = (
        f"Group the following {len(unique_states)} canonical UI states into behaviour flows "
        f"and infer ordered transitions:\n"
        f"{json.dumps(unique_states, indent=2)}\n"
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
            flow_discovery_result_id=f"fdr_{run_id[-6:]}_{uuid.uuid4().hex[:8]}",
            source_canonical_state_set_id=canonical_state_set.get("ui_state_package_id") or canonical_state_set.get("canonical_state_set_id", "unknown_set"),
            candidate_flows=[],
            semantic_clusters=[],
            uncertain_relations=[],
            discovery_warnings=[str(response.error or "LLM_FAILED")],
        ).model_dump()
        err["report"] = {"error": str(response.error)}
        return err

    result: UIFlowDiscoveryResult = response.parsed_output

    flow_id_map: Dict[str, str] = {}
    transition_id_map: Dict[str, str] = {}

    for flow_data in result.candidate_flows:
        db_flow_id = _generate_flow_id(run_id)
        flow_id_map[flow_data.flow_id] = db_flow_id

        # Basic metadata
        flow_row = Flow(
            id=db_flow_id,
            run_id=run_id,
            name=flow_data.flow_name,
            flow_type=flow_data.flow_type,
            flow_label=flow_data.flow_name,
            input_level="AGENT_3_FLOW_DISCOVERY",
            entry_state_id=flow_data.ordered_states[0] if flow_data.ordered_states else None,
            ordered_state_ids_json={"ids": flow_data.ordered_states},
            user_goal=flow_data.user_goal,
            confidence=0.0,  # Calculated downstream or kept as 0.0
        )
        db.add(flow_row)

        # Map Direct Transitions
        for tr_data in flow_data.transitions:
            db_tr_id = _generate_transition_id(run_id)
            transition_id_map[f"{flow_data.flow_id}:{tr_data.from_state}:{tr_data.to_state}"] = db_tr_id
            
            tr_row = FlowTransition(
                id=db_tr_id,
                run_id=run_id,
                flow_id=db_flow_id,
                from_state_id=tr_data.from_state,
                to_state_id=tr_data.to_state,
                transition_type="direct_transition",
                trigger_json=tr_data.trigger_action.model_dump(),
                hypothesized_action=_hypothesized_action_from_a3_trigger(tr_data.trigger_action),
                ordering_strength=tr_data.evidence_level,
                transition_basis=tr_data.reasoning_pattern,
                supporting_evidence_refs_json={
                    "source": tr_data.source_evidence,
                    "target": tr_data.target_evidence
                },
                reason=tr_data.reasoning_pattern,
                evidence_json={
                    "assumptions": tr_data.assumptions,
                    "warnings": tr_data.warnings
                }
            )
            db.add(tr_row)

        # Map Alternative Outcomes
        for alt_data in flow_data.alternative_outcomes:
            for outcome_state in alt_data.outcome_states:
                db_tr_id = _generate_transition_id(run_id)
                tr_row = FlowTransition(
                    id=db_tr_id,
                    run_id=run_id,
                    flow_id=db_flow_id,
                    from_state_id=alt_data.source_state,
                    to_state_id=outcome_state,
                    transition_type="alternative_outcome",
                    trigger_json=alt_data.trigger_action.model_dump(),
                    hypothesized_action=_hypothesized_action_from_a3_trigger(alt_data.trigger_action),
                    ordering_strength=alt_data.evidence_level,
                    reason=alt_data.reason,
                    evidence_json={
                        "warnings": alt_data.warnings
                    }
                )
                db.add(tr_row)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    out = result.model_dump()
    for flow_dict in out.get("candidate_flows") or []:
        old_fid = flow_dict.get("flow_id")
        if old_fid in flow_id_map:
            flow_dict["flow_id"] = flow_id_map[old_fid]
        
        for tr_dict in flow_dict.get("transitions") or []:
            # Note: transition IDs are no longer in the new prompt output, 
            # we generated them during DB insertion. 
            # If we need them in the output, we should add them to the dict.
            # For now, let's just ensure the flow_id is correct.
            pass

    report = {
        "candidate_flow_count": len(result.candidate_flows),
        "semantic_cluster_count": len(result.semantic_clusters),
        "uncertain_relation_count": len(result.uncertain_relations),
        "warnings": result.discovery_warnings,
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("ui_flow_discovery_completed", run_id=run_id, duration_ms=duration_ms)

    out["report"] = report
    return out
