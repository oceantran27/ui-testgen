"""
BDD Scenario Generation Service — Agent 6.
Generates Gherkin/BDD scenarios from inferred user intents.
"""
import json
import time
import uuid
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.behaviour_scenario import BehaviourScenario
from app.model_providers import model_adapter
from app.model_providers.base import NonRetryableModelError
from app.model_providers.schemas import BDDScenarioGenerationResult, ScenarioGenerationSummaryA6
from app.core.prompt_manager import prompt_manager


def _generate_behaviour_scenario_id() -> str:
    """behaviour_scenarios.id is a global PK — never persist LLM ids like scn_001."""
    return f"bs_{uuid.uuid4().hex[:12]}"


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

    behaviour_intents = intent_package.get("behaviour_intents", [])
    if not behaviour_intents:
        return BDDScenarioGenerationResult(
            test_scenarios=[],
            unresolved_scenario_items=[],
            coverage_matrix=[],
            generation_summary=ScenarioGenerationSummaryA6(
                total_behaviour_intents=0,
                total_test_scenarios=0,
                total_unresolved_scenario_items=0,
                coverage_rate=0.0
            )
        ).model_dump()

    system_instruction = prompt_manager.get_prompt("scenario_generation")

    user_instruction = (
        f"Generate BDD scenarios for the following intent package:\n"
        f"{json.dumps(intent_package, indent=2)}"
    )

    try:
        response = await model_adapter.call_text_structured(
            task_name="bdd_scenario_generation",
            run_id=run_id,
            node_name="scenario_generation_node",
            system_instruction=system_instruction,
            user_instruction=user_instruction,
            output_schema=BDDScenarioGenerationResult,
            prompt_name="scenario_generation_prompt",
            prompt_version="v1",
            provider_override=settings.BDD_SCENARIO_GENERATION_MODEL_PROVIDER,
            model_name_override=settings.BDD_SCENARIO_GENERATION_MODEL_NAME,
        )
    except NonRetryableModelError as e:
        logger.error(f"BDD Scenario Generation model call failed after retries: {e}")
        err = BDDScenarioGenerationResult(
            test_scenarios=[],
            unresolved_scenario_items=[],
            coverage_matrix=[],
            generation_summary=ScenarioGenerationSummaryA6(
                total_behaviour_intents=len(behaviour_intents),
                total_test_scenarios=0,
                total_unresolved_scenario_items=0,
                coverage_rate=0.0,
            ),
        ).model_dump()
        err["report"] = {"error": str(e), "recoverable": True}
        duration_ms = int((time.time() - start_time) * 1000)
        log_event("bdd_scenario_generation_completed", run_id=run_id, duration_ms=duration_ms)
        return err

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"BDD Scenario Generation failed: {response.error}")
        err = BDDScenarioGenerationResult(
            test_scenarios=[],
            unresolved_scenario_items=[],
            coverage_matrix=[],
            generation_summary=ScenarioGenerationSummaryA6(
                total_behaviour_intents=len(behaviour_intents),
                total_test_scenarios=0,
                total_unresolved_scenario_items=0,
                coverage_rate=0.0
            )
        ).model_dump()
        err["report"] = {"error": str(response.error)}
        return err

    result: BDDScenarioGenerationResult = response.parsed_output

    scenario_id_map: Dict[str, str] = {}
    for scn in result.test_scenarios:
        if scn.scenario_id not in scenario_id_map:
            scenario_id_map[scn.scenario_id] = _generate_behaviour_scenario_id()

    for scn in result.test_scenarios:
        db_id = scenario_id_map[scn.scenario_id]
        bs = BehaviourScenario(
            id=db_id,
            run_id=run_id,
            flow_id=scn.source_flow_id,
            intent_id=scn.source_intent_id,
            feature=scn.source_flow_name,
            scenario_title=scn.scenario_name,
            scenario_type=scn.scenario_type,
            gherkin_text="\n".join(scn.gherkin),
            bdd_steps_json={"steps": [s.model_dump() for s in scn.steps]},
            evidence_json={
                "assertions": [a.model_dump() for a in scn.assertions],
                "test_data": [d.model_dump() for d in scn.test_data],
                "preconditions": scn.preconditions,
                "test_objective": scn.test_objective
            },
            assumptions_json={"items": scn.assumptions},
            warnings_json={"items": scn.warnings},
            initial_confidence=1.0 if scn.confidence == "high" else 0.5 if scn.confidence == "medium" else 0.2,
            confidence_label=scn.confidence,
            status="draft",
            grounding_mode="grounded",
        )
        db.add(bs)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("bdd_scenario_generation_completed", run_id=run_id, duration_ms=duration_ms)

    out = result.model_dump()
    for sc in out.get("test_scenarios") or []:
        old_sid = sc.get("scenario_id")
        if isinstance(old_sid, str) and old_sid in scenario_id_map:
            sc["scenario_id"] = scenario_id_map[old_sid]
    
    out["report"] = {
        "generated_scenario_count": len(result.test_scenarios),
        "unresolved_count": len(result.unresolved_scenario_items),
        "coverage_rate": result.generation_summary.coverage_rate
    }
    return out
