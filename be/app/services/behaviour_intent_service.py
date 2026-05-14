"""
Behaviour Intent Inference Service — Agent 5.
Infers user intentions and outcomes from validated UI flows.
"""
import json
import time
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


def _persist_intent_row(
    run_id: str,
    intent: BehaviourIntentA5,
) -> BehaviourIntent:
    return BehaviourIntent(
        id=intent.intent_id,
        run_id=run_id,
        flow_id=intent.source_flow_id,
        source_flow_name=intent.source_flow_name,
        source_flow_type=intent.source_flow_type,
        source_transition_indexes_json={"indexes": intent.source_transition_indexes},
        source_outcome_state=intent.source_outcome_state,
        behaviour_name=intent.behaviour_name,
        intent_type=intent.intent_type,
        test_path=intent.test_path,
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


async def run_behaviour_intent_inference(
    db: AsyncSession,
    run_id: str,
    flow_discovery_result: Dict[str, Any],
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("behaviour_intent_inference_started", run_id=run_id)

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

    system_instruction = prompt_manager.get_prompt("behaviour_intent")

    user_instruction = (
        "Infer behaviour intents from the following UI flow package:\n"
        f"{json.dumps(flow_discovery_result, indent=2)}"
    )

    response = await model_adapter.call_text_structured(
        task_name="behaviour_intent_inference",
        run_id=run_id,
        node_name="behaviour_intent_inference_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=BehaviourIntentInferenceResult,
        provider_override=settings.BEHAVIOUR_INTENT_MODEL_PROVIDER,
        model_name_override=settings.BEHAVIOUR_INTENT_MODEL_NAME,
        prompt_name="behaviour_intent_inference_prompt",
        prompt_version="v1",
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Behaviour Intent Inference failed: {response.error}")
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
        db.add(_persist_intent_row(run_id, intent))

    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("behaviour_intent_inference_completed", run_id=run_id, duration_ms=duration_ms)

    return result.model_dump()
