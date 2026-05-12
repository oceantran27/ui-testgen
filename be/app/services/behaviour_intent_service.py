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
    BehaviourIntentAlternativeA5,
    BehaviourIntentInferenceResult,
    BehaviourIntentPrimaryA5,
)
from app.core.prompt_manager import prompt_manager


def _persist_intent_row(
    run_id: str,
    flow_id: str,
    intent: BehaviourIntentPrimaryA5 | BehaviourIntentAlternativeA5,
) -> BehaviourIntent:
    is_alt = isinstance(intent, BehaviourIntentAlternativeA5)
    pre = {}
    main_act = {}
    obs_res = {}
    if not is_alt:
        p = intent  # type: BehaviourIntentPrimaryA5
        pre = p.observable_precondition.model_dump()
        main_act = p.main_user_action.model_dump()
        obs_res = p.observable_result.model_dump()
        
    return BehaviourIntent(
        id=intent.intent_id,
        run_id=run_id,
        flow_id=flow_id,
        intent_name=intent.intent_name,
        behaviour_domain=intent.domain,
        behaviour_outcome=intent.behaviour_outcome,
        outcome_certainty=intent.outcome_certainty,
        user_goal=intent.user_goal,
        intent_scope=intent.intent_scope,
        observable_precondition_json=pre,
        main_user_action_json=main_act,
        observable_result_json=obs_res,
        grounding_evidence_json=intent.grounding_evidence.model_dump(),
        grounding_level=intent.grounding_level,
        ambiguity_json=intent.ambiguity.model_dump(),
        confidence=0.0,
        confidence_label="high",
        scenario_type_hint="positive_behaviour",
        expected_grounding=intent.grounding_level,
    )


async def run_behaviour_intent_inference(
    db: AsyncSession,
    run_id: str,
    flow_discovery_result: Dict[str, Any],
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("behaviour_intent_inference_started", run_id=run_id)

    flows = flow_discovery_result.get("flows", [])
    if not flows:
        return BehaviourIntentInferenceResult(
            intent_package_id="",
            source_flow_discovery_result_id=flow_discovery_result.get(
                "flow_discovery_result_id", ""
            ),
            flow_intents=[],
            package_warnings=["NO_FLOWS_DISCOVERED"],
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
            intent_package_id="",
            source_flow_discovery_result_id=flow_discovery_result.get(
                "flow_discovery_result_id", ""
            ),
            flow_intents=[],
            package_warnings=[str(response.error or "LLM_FAILED")],
        ).model_dump()
        err["report"] = {"error": str(response.error)}
        return err

    result: BehaviourIntentInferenceResult = response.parsed_output

    for flow_intent in result.flow_intents:
        db.add(_persist_intent_row(run_id, flow_intent.flow_id, flow_intent.primary_intent))
        for alt in flow_intent.alternative_intents:
            db.add(_persist_intent_row(run_id, flow_intent.flow_id, alt))

    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("behaviour_intent_inference_completed", run_id=run_id, duration_ms=duration_ms)

    return result.model_dump()
