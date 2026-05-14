"""
Scenario Validation Service — Agent 7.
Acts as a judge to audit generated scenarios against UI evidence.
"""
import datetime
import json
import time
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.behaviour_scenario import BehaviourScenario
from app.model_providers import model_adapter
from app.model_providers.schemas import FinalOutputSummaryA7, ScenarioValidationResult
from app.services.json_report_artifact import save_json_report_artifact

_SCENARIO_VALIDATION_ARTIFACT = "scenario_validation_report"
_SCENARIO_VALIDATION_SUBPATH = "validation/scenario_validation_report.json"


async def _persist_scenario_validation_report(
    db: AsyncSession, run_id: str, payload: Dict[str, Any]
) -> None:
    await save_json_report_artifact(
        db,
        run_id=run_id,
        artifact_type=_SCENARIO_VALIDATION_ARTIFACT,
        node_name="scenario_validation_node",
        storage_subpath=_SCENARIO_VALIDATION_SUBPATH,
        payload=payload,
    )
    await db.commit()

async def run_scenario_validation(
    db: AsyncSession,
    run_id: str,
    scenario_draft_package: Dict[str, Any],
    ui_state_package: Optional[Dict[str, Any]] = None,
    flow_discovery_result: Optional[Dict[str, Any]] = None,
    intent_package: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("scenario_validation_started", run_id=run_id)

    test_scenarios = scenario_draft_package.get("test_scenarios", [])
    if not test_scenarios:
        empty = ScenarioValidationResult(
            validated_scenarios=[],
            final_output_summary=FinalOutputSummaryA7(),
            package_warnings=["NO_SCENARIOS"],
        ).model_dump()
        await _persist_scenario_validation_report(db, run_id, empty)
        return empty

    system_instruction = prompt_manager.get_prompt("scenario_validation")

    # Construct enriched user instruction for multi-layer validation
    validation_input = {
        "test_scenarios": test_scenarios,
        "behaviour_intents": intent_package.get("behaviour_intents", []) if intent_package else [],
        "candidate_flows": flow_discovery_result.get("candidate_flows", []) if flow_discovery_result else [],
        "ui_state_evidence": ui_state_package.get("extracted_states", []) if ui_state_package else [],
        "unresolved_flow_items": intent_package.get("unresolved_flow_items", []) if intent_package else [],
    }

    user_instruction = (
        "Audit the following scenario draft package against the UI evidence and pipeline context:\n"
        f"{json.dumps(validation_input, indent=2)}"
    )

    response = await model_adapter.call_text_structured(
        task_name="scenario_validation",
        run_id=run_id,
        node_name="scenario_validation_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=ScenarioValidationResult,
        prompt_name="scenario_validation_prompt",
        prompt_version="v1",
        provider_override=settings.SCENARIO_VALIDATION_MODEL_PROVIDER,
        model_name_override=settings.SCENARIO_VALIDATION_MODEL_NAME,
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Scenario Validation failed: {response.error}")
        err = ScenarioValidationResult(
            validated_scenarios=[],
            final_output_summary=FinalOutputSummaryA7(),
            package_warnings=[str(response.error or "LLM_FAILED")],
        ).model_dump()
        err["report"] = {"error": str(response.error)}
        await _persist_scenario_validation_report(db, run_id, err)
        return err

    result: ScenarioValidationResult = response.parsed_output

    for vscn in result.validated_scenarios:
        result_db = await db.execute(
            select(BehaviourScenario).where(
                BehaviourScenario.id == vscn.scenario_id,
                BehaviourScenario.run_id == run_id,
            )
        )
        bs = result_db.scalar_one_or_none()
        if bs:
            bs.validation_status = vscn.validation_status
            bs.grounding_score = vscn.grounding_score
            bs.evidence_coverage_score = vscn.evidence_coverage_score
            bs.final_reliability = vscn.final_reliability
            bs.scores_json = vscn.scores.model_dump()
            bs.step_audits_json = {"audits": [a.model_dump() for a in vscn.step_audits]}
            bs.hallucination_flags_json = vscn.hallucination_flags.model_dump()
            bs.revision_suggestions_json = {
                "items": [r.model_dump() for r in vscn.revision_suggestions]
            }
            bs.acceptance_decision_json = vscn.acceptance_decision.model_dump()
            bs.validated_at = datetime.datetime.utcnow()

    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("scenario_validation_completed", run_id=run_id, duration_ms=duration_ms)

    dumped = result.model_dump()
    await _persist_scenario_validation_report(db, run_id, dumped)
    return dumped
