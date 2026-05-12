"""
BDD Scenario Generation Service — Agent 6.
Generates Gherkin/BDD scenarios from inferred user intents.
"""
import json
import time
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.behaviour_scenario import BehaviourScenario
from app.model_providers import model_adapter
from app.model_providers.schemas import BDDScenarioGenerationResult
from app.core.prompt_manager import prompt_manager


async def run_bdd_scenario_generation(
    db: AsyncSession, 
    run_id: str, 
    intent_package: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Main entry point for Agent 6 generation.
    """
    start_time = time.time()
    log_event("bdd_scenario_generation_started", run_id=run_id)

    flow_intents = intent_package.get("flow_intents", [])
    if not flow_intents:
        return BDDScenarioGenerationResult(
            scenario_draft_package_id="",
            source_intent_package_id=intent_package.get("intent_package_id", ""),
            features=[],
            skipped_intents=[],
            package_warnings=["NO_INTENTS"],
        ).model_dump()

    system_instruction = prompt_manager.get_prompt("scenario_generation")

    user_instruction = (
        f"Generate BDD scenarios for the following intent package:\n"
        f"{json.dumps(intent_package, indent=2)}"
    )

    response = await model_adapter.call_text_structured(
        task_name="bdd_scenario_generation",
        run_id=run_id,
        node_name="scenario_generation_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=BDDScenarioGenerationResult,
        prompt_name="scenario_generation_prompt",
        prompt_version="v1",
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"BDD Scenario Generation failed: {response.error}")
        err = BDDScenarioGenerationResult(
            scenario_draft_package_id="",
            source_intent_package_id=intent_package.get("intent_package_id", ""),
            features=[],
            skipped_intents=[],
            package_warnings=[str(response.error or "LLM_FAILED")],
        ).model_dump()
        err["report"] = {"error": str(response.error)}
        return err

    result: BDDScenarioGenerationResult = response.parsed_output
    
    for feature in result.features:
        for scn in feature.scenarios:
            if not scn.linked_intent_ids:
                logger.warning("Skipping scenario %s: no linked_intent_ids", scn.scenario_id)
                continue
            bs = BehaviourScenario(
                id=scn.scenario_id,
                run_id=run_id,
                flow_id=scn.linked_flow_id,
                intent_id=scn.linked_intent_ids[0],
                feature=feature.feature_name,
                scenario_title=scn.scenario_title,
                scenario_type=scn.scenario_type,
                gherkin_text=scn.gherkin_text,
                bdd_steps_json={"steps": [s.model_dump() for s in scn.bdd_steps]},
                status="draft",
                grounding_mode="grounded",
            )
            db.add(bs)

    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("bdd_scenario_generation_completed", run_id=run_id, duration_ms=duration_ms)

    return result.model_dump()
