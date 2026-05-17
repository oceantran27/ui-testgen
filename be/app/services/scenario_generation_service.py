"""
BDD Scenario Generation Service — Agent 6.
Generates Gherkin/BDD scenarios from inferred user intents (deterministic; no LLM).
"""
import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log_event, logger
from app.db.models.behaviour_scenario import BehaviourScenario
from app.model_providers.schemas import (
    AssertionA6,
    BDDScenarioGenerationResult,
    BehaviourIntentA5,
    CoverageMatrixItemA6,
    ScenarioGenerationSummaryA6,
    TestDataA6,
    TestScenarioA6,
    TestScenarioStepA6,
    UnresolvedScenarioItemA6,
)
from app.services.behaviour_contract_service import map_test_path


def _generate_behaviour_scenario_id() -> str:
    """behaviour_scenarios.id is a global PK — never persist LLM ids like scn_001."""
    return f"bs_{uuid.uuid4().hex[:12]}"


def _precheck_behaviour_intent_for_scenarios(intent: BehaviourIntentA5) -> Optional[UnresolvedScenarioItemA6]:
    """
    Fail fast unresolved items when deterministic generation would produce unusable drafts.
    """
    if not (intent.start_state or "").strip() or not (intent.end_state or "").strip():
        return UnresolvedScenarioItemA6(
            item_type="missing_critical_field",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="Missing start_state or end_state",
        )

    ta = intent.trigger_action
    trigger_fragments = (ta.text or []) if ta else []
    trigger_text_nonempty = any(str(t).strip() for t in trigger_fragments)
    if not ta or not trigger_text_nonempty:
        return UnresolvedScenarioItemA6(
            item_type="missing_critical_field",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="trigger_action missing non-empty text",
        )

    if not (intent.expected_result or "").strip():
        return UnresolvedScenarioItemA6(
            item_type="insufficient_expected_result",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="expected_result missing or whitespace-only",
        )

    ft = intent.source_flow_type or ""
    if ft in ("ordered_sequence", "branching_flow") and not (intent.source_transition_ids or []):
        return UnresolvedScenarioItemA6(
            item_type="insufficient_traceability",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="source_transition_ids required for ordered_sequence / branching_flow",
        )

    if intent.start_state != intent.end_state and not intent.user_actions:
        return UnresolvedScenarioItemA6(
            item_type="invalid_intent",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="Cross-state intent requires user_actions steps",
        )

    itype = (intent.intent_type or "").lower()
    if itype in ("positive", "validation") and not intent.expected_ui_evidence:
        return UnresolvedScenarioItemA6(
            item_type="insufficient_evidence",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason=f"intent_type {itype!r} requires expected_ui_evidence",
        )
    if itype == "negative" and not intent.negative_expectations:
        return UnresolvedScenarioItemA6(
            item_type="insufficient_evidence",
            source_intent_id=intent.intent_id,
            source_flow_id=intent.source_flow_id,
            reason="intent_type negative requires negative_expectations",
        )

    return None


async def run_bdd_scenario_generation(
    db: AsyncSession,
    run_id: str,
    intent_package: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Agent 6 — Programmatic BDD Scenario Generation.
    Deterministic: BehaviourIntentA5 → TestScenarioA6 → BehaviourScenario rows (no revision/audit coupling).
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
                coverage_rate=0.0,
            ),
        ).model_dump()

    behaviour_intents = [BehaviourIntentA5.model_validate(i) for i in behaviour_intents_raw]

    test_scenarios: List[TestScenarioA6] = []
    unresolved_items: List[UnresolvedScenarioItemA6] = []
    coverage_matrix: List[CoverageMatrixItemA6] = []

    for intent in behaviour_intents:
        pre_issue = _precheck_behaviour_intent_for_scenarios(intent)
        if pre_issue:
            unresolved_items.append(pre_issue)
            coverage_matrix.append(
                CoverageMatrixItemA6(
                    intent_id=intent.intent_id,
                    coverage_status="unresolved",
                    reason=pre_issue.reason,
                )
            )
            continue

        scenario_id = f"scn_{intent.intent_id[-8:]}"
        scenario_name = intent.behaviour_name.strip().capitalize()

        steps: List[TestScenarioStepA6] = []
        step_counter = 1

        for i, pre in enumerate(intent.preconditions):
            steps.append(
                TestScenarioStepA6(
                    step_number=step_counter,
                    keyword="Given" if i == 0 else "And",
                    text=pre,
                    source="precondition",
                )
            )
            step_counter += 1

        if not intent.preconditions:
            steps.append(
                TestScenarioStepA6(
                    step_number=step_counter,
                    keyword="Given",
                    text=f"User is on {intent.start_state}",
                    source="precondition",
                )
            )
            step_counter += 1

        test_data_list: List[TestDataA6] = []
        for td in intent.test_data_requirements:
            placeholder = f"<{td.value_type}>"
            test_data_list.append(
                TestDataA6(
                    data_name=td.field_or_input,
                    value_placeholder=placeholder,
                    source_requirement=td.reason,
                    required=td.required,
                    reason=td.reason,
                )
            )
            steps.append(
                TestScenarioStepA6(
                    step_number=step_counter,
                    keyword="And",
                    text=f"The user has {td.field_or_input} as {placeholder}",
                    source="test_data",
                )
            )
            step_counter += 1

        for i, act in enumerate(intent.user_actions):
            steps.append(
                TestScenarioStepA6(
                    step_number=step_counter,
                    keyword="When" if i == 0 else "And",
                    text=act,
                    source="user_action",
                )
            )
            step_counter += 1

        steps.append(
            TestScenarioStepA6(
                step_number=step_counter,
                keyword="Then",
                text=intent.expected_result,
                source="expected_result",
            )
        )
        step_counter += 1

        assertions: List[AssertionA6] = [
            AssertionA6(
                assertion_type="state_transition",
                expected=intent.end_state,
                source="expected_result",
                ui_text_grounding_required=False,
            )
        ]

        for ev in intent.expected_ui_evidence:
            steps.append(
                TestScenarioStepA6(
                    step_number=step_counter,
                    keyword="And",
                    text=f"The UI shows: {ev}",
                    source="expected_ui_evidence",
                )
            )
            step_counter += 1

            a_type = "ui_evidence_present"
            if "feedback" in ev.lower():
                a_type = "feedback_visible"
            elif "purpose" in ev.lower():
                a_type = "screen_purpose_matched"

            assertions.append(
                AssertionA6(
                    assertion_type=a_type,
                    expected=ev,
                    source="expected_ui_evidence",
                )
            )

        for neg in intent.negative_expectations:
            steps.append(
                TestScenarioStepA6(
                    step_number=step_counter,
                    keyword="And",
                    text=f"The user should NOT see: {neg}",
                    source="negative_expectation",
                )
            )
            step_counter += 1

            assertions.append(
                AssertionA6(
                    assertion_type=(
                        "feedback_not_visible" if "feedback" in neg.lower() else "state_not_reached"
                    ),
                    expected=neg,
                    source="negative_expectation",
                )
            )

        scenario = TestScenarioA6(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            scenario_type=map_test_path(intent.intent_type),
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
            confidence=intent.confidence,
        )
        test_scenarios.append(scenario)
        coverage_matrix.append(
            CoverageMatrixItemA6(
                intent_id=intent.intent_id,
                scenario_id=scenario_id,
                coverage_status="covered",
                reason="Synthetically generated from intent",
            )
        )

    result = BDDScenarioGenerationResult(
        test_scenarios=test_scenarios,
        unresolved_scenario_items=unresolved_items,
        coverage_matrix=coverage_matrix,
        generation_summary=ScenarioGenerationSummaryA6(
            total_behaviour_intents=len(behaviour_intents),
            total_test_scenarios=len(test_scenarios),
            total_unresolved_scenario_items=len(unresolved_items),
            coverage_rate=len(test_scenarios) / len(behaviour_intents) if behaviour_intents else 0.0,
        ),
    )

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
                "test_objective": scn.test_objective,
            },
            assumptions_json={"items": scn.assumptions},
            warnings_json={"items": scn.warnings},
            initial_confidence=1.0
            if scn.confidence == "high"
            else 0.5
            if scn.confidence == "medium"
            else 0.2,
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

    out = result.model_dump()
    for sc in out.get("test_scenarios") or []:
        old_sid = sc.get("scenario_id")
        if old_sid in scenario_db_id_map:
            sc["scenario_id"] = scenario_db_id_map[old_sid]

        sc_steps = sc.get("steps", [])
        sc["gherkin"] = [f"Scenario: {sc.get('scenario_name', '')}"] + [
            f"{s.get('keyword')} {s.get('text')}" for s in sc_steps
        ]

    for cm in out.get("coverage_matrix") or []:
        old_sid = cm.get("scenario_id")
        if old_sid and old_sid in scenario_db_id_map:
            cm["scenario_id"] = scenario_db_id_map[old_sid]

    out["report"] = {
        "generated_scenario_count": len(test_scenarios),
        "unresolved_count": len(unresolved_items),
        "coverage_rate": result.generation_summary.coverage_rate,
        "mode": "deterministic_python",
        "auto_revision_retry": False,
    }
    return out
