"""
Scenario Evidence Audit Service — Agent 7.
Acts as a judge to audit generated scenarios against UI evidence and screen intents.
"""
import datetime
import json
import math
import time
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.behaviour_scenario import BehaviourScenario
from app.model_providers import model_adapter
from app.model_providers.schemas import FinalOutputSummaryA7, ScenarioValidationResult, ValidatedScenarioA7
from app.constants.validation_artifacts import SCENARIO_EVIDENCE_AUDIT_REPORT_ARTIFACT
from app.services.json_report_artifact import save_json_report_artifact

_SCENARIO_VALIDATION_ARTIFACT = SCENARIO_EVIDENCE_AUDIT_REPORT_ARTIFACT
_SCENARIO_VALIDATION_SUBPATH = "validation/scenario_evidence_audit_report.json"


def _aggregate_final_summary(validated: Sequence[ValidatedScenarioA7]) -> FinalOutputSummaryA7:
    """Recompute summary from merged batches (per-batch LLM summaries are not merged)."""

    def cnt(status: str) -> int:
        return sum(1 for v in validated if (v.validation_status or "").lower() == status)

    return FinalOutputSummaryA7(
        validated_count=cnt("validated"),
        rejected_count=cnt("rejected"),
        low_confidence_count=cnt("low_confidence"),
        needs_revision_count=cnt("needs_revision"),
        total_count=len(validated),
    )


async def _persist_scenario_validation_report(
    db: AsyncSession, run_id: str, payload: Dict[str, Any]
) -> None:
    await save_json_report_artifact(
        db,
        run_id=run_id,
        artifact_type=_SCENARIO_VALIDATION_ARTIFACT,
        node_name="scenario_evidence_audit_node",
        storage_subpath=_SCENARIO_VALIDATION_SUBPATH,
        payload=payload,
    )
    await db.commit()

async def run_scenario_evidence_audit(
    db: AsyncSession,
    run_id: str,
    scenario_draft_package: Dict[str, Any],
    ui_state_package: Optional[Dict[str, Any]] = None,
    flow_discovery_result: Optional[Dict[str, Any]] = None,
    intent_package: Optional[Dict[str, Any]] = None,
    screen_intent_package: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("scenario_evidence_audit_started", run_id=run_id)

    test_scenarios = scenario_draft_package.get("test_scenarios", [])
    if not test_scenarios:
        empty = ScenarioValidationResult(
            validated_scenarios=[],
            final_output_summary=FinalOutputSummaryA7(),
            package_warnings=["NO_SCENARIOS"],
        ).model_dump()
        await _persist_scenario_validation_report(db, run_id, empty)
        return empty

    system_instruction = prompt_manager.get_prompt("prompt_scenario_evidence_audit")

    shared_context = {
        "behaviour_intents": intent_package.get("behaviour_intents", []) if intent_package else [],
        "candidate_flows": flow_discovery_result.get("candidate_flows", []) if flow_discovery_result else [],
        "screen_intent_package": screen_intent_package.get("screen_intent_catalog", []) if screen_intent_package else [],
        "ui_state_evidence": ui_state_package.get("extracted_states", []) if ui_state_package else [],
    }

    batch_size = max(1, settings.SCENARIO_EVIDENCE_AUDIT_SCENARIO_BATCH_SIZE)
    total_batches = math.ceil(len(test_scenarios) / batch_size)

    validated_accum: List[ValidatedScenarioA7] = []
    warnings_accum: List[str] = []

    if total_batches > 1:
        logger.info(
            "scenario_evidence_audit batching: run=%s scenarios=%s batch_size=%s batches=%s",
            run_id,
            len(test_scenarios),
            batch_size,
            total_batches,
        )

    for batch_idx, start in enumerate(range(0, len(test_scenarios), batch_size)):
        chunk = test_scenarios[start : start + batch_size]
        validation_input = {**shared_context, "test_scenarios": chunk}

        batch_header = ""
        if total_batches > 1:
            batch_header = (
                f"This is BATCH {batch_idx + 1} of {total_batches}. "
                "Audit ONLY the test_scenarios in this batch. "
                "Return validated_scenarios with exactly one entry per scenario in this batch "
                "(matching scenario_id).\n\n"
            )

        user_instruction = batch_header + (
            "Audit the following scenario draft package against the UI evidence and pipeline context:\n"
            f"{json.dumps(validation_input, indent=2)}"
        )

        response = await model_adapter.call_text_structured(
            task_name="scenario_evidence_audit",
            run_id=run_id,
            node_name="scenario_evidence_audit_node",
            system_instruction=system_instruction,
            user_instruction=user_instruction,
            output_schema=ScenarioValidationResult,
            prompt_name="prompt_scenario_evidence_audit",
            prompt_version="v1",
            provider_override=settings.SCENARIO_VALIDATION_MODEL_PROVIDER,
            model_name_override=settings.SCENARIO_VALIDATION_MODEL_NAME,
        )

        if response.status.value != "success" or not response.parsed_output:
            logger.error(
                "Scenario Evidence Audit failed (batch %s/%s): %s",
                batch_idx + 1,
                total_batches,
                response.error,
            )
            err = ScenarioValidationResult(
                validated_scenarios=[],
                final_output_summary=FinalOutputSummaryA7(),
                package_warnings=[
                    f"BATCH_{batch_idx + 1}_OF_{total_batches}: {response.error or 'LLM_FAILED'}"
                ],
            ).model_dump()
            err["report"] = {"error": str(response.error), "failed_batch": batch_idx + 1}
            await _persist_scenario_validation_report(db, run_id, err)
            return err

        batch_result: ScenarioValidationResult = response.parsed_output
        validated_accum.extend(batch_result.validated_scenarios)
        warnings_accum.extend(batch_result.package_warnings)

    result = ScenarioValidationResult(
        validated_scenarios=validated_accum,
        final_output_summary=_aggregate_final_summary(validated_accum),
        package_warnings=warnings_accum,
    )

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
            bs.grounding_score = vscn.scores.flow_grounding_score
            bs.evidence_coverage_score = vscn.scores.evidence_grounding_score
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
    log_event("scenario_evidence_audit_completed", run_id=run_id, duration_ms=duration_ms)

    dumped = result.model_dump()
    await _persist_scenario_validation_report(db, run_id, dumped)
    return dumped
