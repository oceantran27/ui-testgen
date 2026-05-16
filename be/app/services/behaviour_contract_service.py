"""
Behaviour Contract Builder Service — Agent 5.
Infers behaviour contracts (Test Intents) from validated intent-aware UI flows.
"""
import json
import time
import uuid
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.behaviour_intent import BehaviourIntent
from app.model_providers import model_adapter
from app.model_providers.schemas import (
    BehaviourIntentA5,
    BehaviourIntentInferenceResult,
)
from app.core.prompt_manager import prompt_manager


def _generate_behaviour_intent_id(run_id: str) -> str:
    """behaviour_intents.id is a global PK — never persist LLM ids directly."""
    return f"bi_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


def _map_test_path(intent_type: str) -> str:
    mapping = {
        "positive": "happy_path",
        "negative": "negative_path",
        "validation": "validation_path",
        "navigation": "navigation_path",
        "recovery": "recovery_path",
        "registration": "registration_path",
        "access_control": "access_control_path",
        "data_entry": "data_entry_path",
    }
    return mapping.get(intent_type, "unknown_path")


def _persist_intent_row(
    run_id: str,
    intent: BehaviourIntentA5,
) -> BehaviourIntent:
    test_path = _map_test_path(intent.intent_type)
    return BehaviourIntent(
        id=intent.intent_id,
        run_id=run_id,
        flow_id=intent.source_flow_id,
        source_flow_name=intent.source_flow_name,
        source_flow_type=intent.source_flow_type,
        source_transition_indexes_json={"indexes": intent.source_transition_indexes},
        source_outcome_state=intent.source_outcome_state,
        source_group_id=intent.source_group_id,
        source_screen_intent_id=intent.source_screen_intent_id,
        source_transition_ids_json={"ids": intent.source_transition_ids},
        behaviour_name=intent.behaviour_name,
        intent_type=intent.intent_type,
        test_path=test_path,
        user_intent=intent.user_intent,
        business_goal=intent.business_goal,
        start_state=intent.start_state,
        end_state=intent.end_state,
        trigger_action_json=intent.trigger_action.model_dump(),
        preconditions_json={"items": intent.preconditions},
        test_data_requirements_json={"items": [i.model_dump() for i in intent.test_data_requirements]},
        user_actions_json={"items": intent.user_actions},
        expected_result=intent.expected_result,
        expected_ui_evidence_json={"items": intent.expected_ui_evidence},
        negative_expectations_json={"items": intent.negative_expectations},
        confidence=intent.confidence,
        assumptions_json={"items": intent.assumptions},
        warnings_json={"items": intent.warnings},
        raw_result_json=intent.model_dump(),
    )


def _pre_filter_flows(flow_discovery_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministically filter out transitions and outcomes that should NOT be converted to scenarios.
    Ensures mutual exclusivity and prevents same-state scenarios.
    """
    for flow in flow_discovery_result.get("candidate_flows", []):
        # 1. Filter transitions
        valid_transitions = []
        for t in flow.get("transitions", []):
            from_st = t.get("from_state")
            to_st = t.get("to_state")
            rel = t.get("relation_type", "direct_transition")
            warnings = " ".join(t.get("warnings", [])).lower()

            # Skip same-state navigation (unless it's a negative outcome with feedback)
            if from_st == to_st and rel != "negative_outcome":
                continue
            
            # Skip if destination is explicitly missing
            if "destination state not included" in warnings or "no distinct target state" in warnings:
                continue
            
            valid_transitions.append(t)
        flow["transitions"] = valid_transitions

        # 2. Filter alternative outcomes
        valid_outcomes = []
        for o in flow.get("alternative_outcomes", []):
            src = o.get("source_state")
            outcomes = o.get("outcome_states", [])
            warnings = " ".join(o.get("warnings", [])).lower()

            # Skip empty outcomes
            if not outcomes:
                continue
            
            # Skip same-state outcomes
            if len(outcomes) == 1 and outcomes[0] == src:
                continue
            
            # Skip if destination is explicitly missing
            if "destination state not included" in warnings or "no distinct target state" in warnings:
                continue

            valid_outcomes.append(o)
        flow["alternative_outcomes"] = valid_outcomes

    return flow_discovery_result


async def run_behaviour_contract_builder(
    db: AsyncSession,
    run_id: str,
    flow_discovery_result: Dict[str, Any],
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("behaviour_contract_builder_started", run_id=run_id)

    # Apply deterministic pre-filtering before passing to LLM
    flow_discovery_result = _pre_filter_flows(flow_discovery_result)

    candidate_flows = flow_discovery_result.get("candidate_flows", [])
    if not candidate_flows:
        return BehaviourIntentInferenceResult(
            behaviour_intents=[],
            unresolved_flow_items=[],
            generation_summary={
                "total_candidate_flows": 0,
                "total_behaviour_intents": 0,
                "total_unresolved_items": 0
            },
        ).model_dump()

    system_instruction = prompt_manager.get_prompt("prompt_behaviour_contract_builder")

    user_instruction = (
        "Infer behaviour contracts from the following Intent-aware UI flow package:\n"
        f"{json.dumps(flow_discovery_result, indent=2)}"
    )

    response = await model_adapter.call_text_structured(
        task_name="behaviour_contract_builder",
        run_id=run_id,
        node_name="behaviour_contract_builder_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=BehaviourIntentInferenceResult,
        provider_override=settings.BEHAVIOUR_INTENT_MODEL_PROVIDER,
        model_name_override=settings.BEHAVIOUR_INTENT_MODEL_NAME,
        prompt_name="prompt_behaviour_contract_builder",
        prompt_version="v1",
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Behaviour Contract Builder failed: {response.error}")
        err = BehaviourIntentInferenceResult(
            behaviour_intents=[],
            unresolved_flow_items=[],
            generation_summary={
                "total_candidate_flows": len(candidate_flows),
                "total_behaviour_intents": 0,
                "total_unresolved_items": 0
            },
        ).model_dump()
        err["report"] = {"error": str(response.error)}
        return err

    result: BehaviourIntentInferenceResult = response.parsed_output

    for intent in result.behaviour_intents:
        intent.intent_id = _generate_behaviour_intent_id(run_id)
        db.add(_persist_intent_row(run_id, intent))

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to commit behaviour contracts for run {run_id}: {e}")
        await db.rollback()
        raise

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("behaviour_contract_builder_completed", run_id=run_id, duration_ms=duration_ms)

    return result.model_dump()
