"""
BDD Scenario Generation Service — Agent 6.
Generates Gherkin/BDD scenarios from inferred user intents.
"""
import json
import time
import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.behaviour_scenario import BehaviourScenario
from app.model_providers import model_adapter
from app.model_providers.base import NonRetryableModelError
from app.model_providers.schemas import BDDScenarioGenerationResult, ScenarioGenerationSummaryA6
from app.services.behaviour_contract_service import _map_test_path


def _generate_behaviour_scenario_id() -> str:
    """behaviour_scenarios.id is a global PK — never persist LLM ids like scn_001."""
    return f"bs_{uuid.uuid4().hex[:12]}"


async def run_bdd_scenario_generation(
    db: AsyncSession, 
    run_id: str, 
    intent_package: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Agent 6 — Programmatic BDD Scenario Generation.
    Optimized: Replaced LLM call with deterministic Python logic.
    """
    start_time = time.time()
    log_event("bdd_scenario_generation_started", run_id=run_id)

    behaviour_intents_raw = intent_package.get("behaviour_intents", [])
    if not behaviour_intents_raw:
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

    # Parse input using Agent 5 schema for safety
    from app.model_providers.schemas import (
        BehaviourIntentA5, 
        TestScenarioA6, 
        TestScenarioStepA6, 
        AssertionA6, 
        TestDataA6,
        UnresolvedScenarioItemA6,
        CoverageMatrixItemA6,
    )
    
    behaviour_intents = [BehaviourIntentA5.model_validate(i) for i in behaviour_intents_raw]
    
    test_scenarios: List[TestScenarioA6] = []
    unresolved_items: List[UnresolvedScenarioItemA6] = []
    coverage_matrix: List[CoverageMatrixItemA6] = []

    for intent in behaviour_intents:
        # 1. Validation
        if not intent.start_state or not intent.end_state or not intent.trigger_action:
            item = UnresolvedScenarioItemA6(
                item_type="missing_critical_field",
                source_intent_id=intent.intent_id,
                source_flow_id=intent.source_flow_id,
                reason="Missing start_state, end_state, or trigger_action"
            )
            unresolved_items.append(item)
            coverage_matrix.append(CoverageMatrixItemA6(
                intent_id=intent.intent_id,
                coverage_status="unresolved",
                reason=item.reason
            ))
            continue

        # 2. Build Scenario Metadata
        scenario_id = f"scn_{intent.intent_id[-8:]}"
        scenario_name = intent.behaviour_name.strip().capitalize()
        
        steps: List[TestScenarioStepA6] = []
        step_counter = 1

        # 3. Map Preconditions -> Given
        for i, pre in enumerate(intent.preconditions):
            steps.append(TestScenarioStepA6(
                step_number=step_counter,
                keyword="Given" if i == 0 else "And",
                text=pre,
                source="precondition"
            ))
            step_counter += 1
        
        if not intent.preconditions:
            steps.append(TestScenarioStepA6(
                step_number=step_counter,
                keyword="Given",
                text=f"User is on {intent.start_state}",
                source="precondition"
            ))
            step_counter += 1

        # 4. Map Test Data -> And (Prepare)
        test_data_list: List[TestDataA6] = []
        for td in intent.test_data_requirements:
            placeholder = f"<{td.value_type}>"
            test_data_list.append(TestDataA6(
                data_name=td.field_or_input,
                value_placeholder=placeholder,
                source_requirement=td.reason,
                required=td.required,
                reason=td.reason
            ))
            steps.append(TestScenarioStepA6(
                step_number=step_counter,
                keyword="And",
                text=f"The user has {td.field_or_input} as {placeholder}",
                source="test_data"
            ))
            step_counter += 1

        # 5. Map User Actions -> When/And
        for i, act in enumerate(intent.user_actions):
            steps.append(TestScenarioStepA6(
                step_number=step_counter,
                keyword="When" if i == 0 else "And",
                text=act,
                source="user_action"
            ))
            step_counter += 1

        # 6. Map Expected Result -> Then
        steps.append(TestScenarioStepA6(
            step_number=step_counter,
            keyword="Then",
            text=intent.expected_result,
            source="expected_result"
        ))
        step_counter += 1

        assertions: List[AssertionA6] = []
        assertions.append(AssertionA6(
            assertion_type="state_reached",
            expected=f"User reaches {intent.end_state}",
            source="expected_result"
        ))

        # 7. Map Expected UI Evidence -> And
        for ev in intent.expected_ui_evidence:
            steps.append(TestScenarioStepA6(
                step_number=step_counter,
                keyword="And",
                text=f"The UI shows: {ev}",
                source="expected_ui_evidence"
            ))
            step_counter += 1
            
            # Simple heuristic for assertion type
            a_type = "ui_evidence_present"
            if "feedback" in ev.lower(): a_type = "feedback_visible"
            elif "purpose" in ev.lower(): a_type = "screen_purpose_matched"
            
            assertions.append(AssertionA6(
                assertion_type=a_type,
                expected=ev,
                source="expected_ui_evidence"
            ))

        # 8. Map Negative Expectations -> And
        for neg in intent.negative_expectations:
            steps.append(TestScenarioStepA6(
                step_number=step_counter,
                keyword="And",
                text=f"The user should NOT see: {neg}",
                source="negative_expectation"
            ))
            step_counter += 1
            
            assertions.append(AssertionA6(
                assertion_type="feedback_not_visible" if "feedback" in neg.lower() else "state_not_reached",
                expected=neg,
                source="negative_expectation"
            ))

        # 9. Finalize Scenario Object
        scenario = TestScenarioA6(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            scenario_type=_map_test_path(intent.intent_type),
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            source_flow_name=intent.source_flow_name,
            source_flow_type=intent.source_flow_type,
            source_screen_intent_id=intent.source_screen_intent_id,
            source_group_id=intent.source_group_id,
            source_transition_ids=intent.source_transition_ids,
            source_transition_indexes=intent.source_transition_indexes,
            start_state=intent.start_state,
            end_state=intent.end_state,
            trigger_action=intent.trigger_action,
            test_objective=f"Verify {intent.user_intent}",
            preconditions=intent.preconditions,
            test_data=test_data_list,
            steps=steps,
            expected_results=[intent.expected_result],
            assertions=assertions,
            assumptions=intent.assumptions,
            warnings=intent.warnings,
            confidence=intent.confidence
        )
        test_scenarios.append(scenario)
        coverage_matrix.append(CoverageMatrixItemA6(
            intent_id=intent.intent_id,
            scenario_id=scenario_id,
            coverage_status="covered",
            reason="Synthetically generated from intent"
        ))

    # 10. Assemble Result
    result = BDDScenarioGenerationResult(
        test_scenarios=test_scenarios,
        unresolved_scenario_items=unresolved_items,
        coverage_matrix=coverage_matrix,
        generation_summary=ScenarioGenerationSummaryA6(
            total_behaviour_intents=len(behaviour_intents),
            total_test_scenarios=len(test_scenarios),
            total_unresolved_scenario_items=len(unresolved_items),
            coverage_rate=len(test_scenarios) / len(behaviour_intents) if behaviour_intents else 0.0
        )
    )

    # 11. Persistence Logic (Refactored from original)
    scenario_db_id_map: Dict[str, str] = {}
    for scn in result.test_scenarios:
        db_id = _generate_behaviour_scenario_id()
        scenario_db_id_map[scn.scenario_id] = db_id
        
        gherkin_lines = [f"Scenario: {scn.scenario_name}"]
        for s in scn.steps:
            gherkin_lines.append(f"  {s.keyword} {s.text}")
        
        bs = BehaviourScenario(
            id=db_id,
            run_id=run_id,
            flow_id=scn.source_flow_id,
            intent_id=scn.source_intent_id,
            feature=scn.source_flow_name,
            scenario_title=scn.scenario_name,
            scenario_type=scn.scenario_type,
            gherkin_text="\n".join(gherkin_lines),
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
    except Exception as e:
        logger.error(f"Failed to commit scenarios for run {run_id}: {e}")
        await db.rollback()
        raise

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("bdd_scenario_generation_completed", run_id=run_id, duration_ms=duration_ms)

    # 12. Final Return Formatting
    out = result.model_dump()
    for sc in out.get("test_scenarios") or []:
        old_sid = sc.get("scenario_id")
        if old_sid in scenario_db_id_map:
            sc["scenario_id"] = scenario_db_id_map[old_sid]
        
        # Ensure gherkin is available for Agent 7 (Validation)
        sc_steps = sc.get("steps", [])
        sc["gherkin"] = [f"Scenario: {sc.get('scenario_name', '')}"] + [
            f"{s.get('keyword')} {s.get('text')}" for s in sc_steps
        ]
    
    out["report"] = {
        "generated_scenario_count": len(test_scenarios),
        "unresolved_count": len(unresolved_items),
        "coverage_rate": result.generation_summary.coverage_rate,
        "mode": "deterministic_python"
    }
    return out
