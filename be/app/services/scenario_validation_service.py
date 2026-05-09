"""
Scenario Grounding & Validation Service — Phase 12 implementation.
Uses LLM-as-a-Judge to validate draft scenarios against UI evidence.
"""
import json
import uuid
import time
import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.behaviour_scenario import BehaviourScenario
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service
from app.model_providers.registry import model_adapter


# ──────────────────────────────────────────────
# Pydantic Schemas for LLM Output
# ──────────────────────────────────────────────

class StepValidationOutput(BaseModel):
    step_id: str
    grounding_level: str = Field(..., description="'grounded', 'partially_grounded', 'inferred', 'ungrounded', 'contradicted'")
    grounding_score: float = Field(..., ge=0.0, le=1.0)
    issues: List[str] = Field(default_factory=list)

class HallucinationFlags(BaseModel):
    element_hallucination: bool
    business_rule_hallucination: bool
    data_hallucination: bool

class ScenarioValidationOutput(BaseModel):
    scenario_id: str
    grounding_score: float = Field(..., ge=0.0, le=1.0)
    evidence_coverage_score: float = Field(..., ge=0.0, le=1.0)
    validation_status: str = Field(..., description="'validated', 'low_confidence', 'needs_revision', 'rejected'")
    step_validations: List[StepValidationOutput]
    hallucination_flags: HallucinationFlags
    validation_issues: List[str] = Field(default_factory=list)
    revision_suggestions: List[str] = Field(default_factory=list)
    final_confidence: float = Field(..., ge=0.0, le=1.0)


# ──────────────────────────────────────────────
# Service Implementation
# ──────────────────────────────────────────────

def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


class ScenarioValidationService:
    """
    LLM-as-a-Judge behaviour scenario validation.
    """

    @staticmethod
    async def run_validation(db: AsyncSession, run_id: str, draft_scenarios: List[Dict[str, Any]], state_catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main entry point for Phase 12 validation.
        """
        start_time = time.time()
        log_event("scenario_validation_started", run_id=run_id, scenario_count=len(draft_scenarios))

        if not draft_scenarios:
            return {"error": "NO_DRAFT_SCENARIOS_FOR_VALIDATION"}

        scenario_ids = [s["scenario_id"] for s in draft_scenarios]
        result = await db.execute(
            select(BehaviourScenario).where(BehaviourScenario.id.in_(scenario_ids))
        )
        scenarios = result.scalars().all()

        validated_list = []
        low_confidence_list = []
        needs_revision_list = []
        rejected_list = []
        
        all_results = []

        for scenario in scenarios:
            log_event("validating_scenario", scenario_id=scenario.id)
            
            # 1. Build Evidence Context
            # We use the state_catalog and elements associated with the flow
            evidence_context = {
                "scenario_title": scenario.scenario_title,
                "gherkin": scenario.gherkin_text,
                "structured_steps": scenario.structured_steps_json,
                "state_catalog": state_catalog # In a real scale, we'd filter to only relevant states
            }

            # 2. Call LLM as Judge
            try:
                system_instruction = (
                    "You are a Senior QA Auditor and Test Design Specialist. "
                    "Your mission is to audit a draft BDD scenario generated from UI screenshots. "
                    "You MUST verify if every step (Given/When/Then) is grounded in the provided UI evidence (state_catalog). "
                    "Identify hallucinations: elements that don't exist, business rules that aren't visible, or data claims without proof. "
                    "Provide a grounding score and a final validation status."
                )
                user_instruction = (
                    f"Audit the following scenario against the UI evidence context.\n\n"
                    f"Evidence Context: {json.dumps(evidence_context, indent=2)}"
                )

                response = await model_adapter.call_text_structured(
                    task_name="scenario_validation",
                    run_id=run_id,
                    node_name="scenario_validation",
                    system_instruction=system_instruction,
                    user_instruction=user_instruction,
                    output_schema=ScenarioValidationOutput,
                    prompt_name="scenario_validation_v1"
                )

                audit: ScenarioValidationOutput = response.parsed_output

                # 3. Update Scenario in DB
                scenario.validation_status = audit.validation_status
                scenario.grounding_score = audit.grounding_score
                scenario.evidence_coverage_score = audit.evidence_coverage_score
                scenario.hallucination_flags_json = audit.hallucination_flags.model_dump()
                scenario.validation_issues_json = {"issues": audit.validation_issues}
                scenario.revision_suggestions_json = {"suggestions": audit.revision_suggestions}
                scenario.final_confidence = audit.final_confidence
                scenario.validated_at = datetime.datetime.utcnow()
                scenario.status = "generated" if audit.validation_status in ["validated", "low_confidence"] else scenario.status

                scenario_summary = {
                    "scenario_id": scenario.id,
                    "title": scenario.scenario_title,
                    "status": scenario.validation_status,
                    "score": scenario.grounding_score,
                    "issues": audit.validation_issues
                }
                
                all_results.append(audit.model_dump())

                if audit.validation_status == "validated":
                    validated_list.append(scenario_summary)
                elif audit.validation_status == "low_confidence":
                    low_confidence_list.append(scenario_summary)
                elif audit.validation_status == "needs_revision":
                    needs_revision_list.append(scenario_summary)
                else:
                    rejected_list.append(scenario_summary)

            except Exception as e:
                logger.exception(f"Failed to validate scenario {scenario.id}: {e}")

        # 4. Finalize and Report
        await db.commit()

        report = {
            "run_id": run_id,
            "summary": {
                "total": len(scenarios),
                "validated": len(validated_list),
                "low_confidence": len(low_confidence_list),
                "needs_revision": len(needs_revision_list),
                "rejected": len(rejected_list)
            },
            "results": all_results,
            "metrics": {
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        }

        if settings.SAVE_SCENARIO_VALIDATION_REPORT:
            report_bytes = json.dumps(report, indent=2).encode("utf-8")
            report_key = f"artifacts/{run_id}/scenario_validation/scenario_grounding_validation_report.json"
            report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

            artifact = Artifact(
                id=_generate_artifact_id(),
                run_id=run_id,
                artifact_type="scenario_grounding_validation_report",
                node_name="scenario_validation",
                storage_uri=report_uri,
            )
            db.add(artifact)
            await db.commit()

        log_event("scenario_validation_completed", run_id=run_id, validated=len(validated_list))

        return {
            "validated_scenarios": validated_list,
            "low_confidence_scenarios": low_confidence_list,
            "needs_revision_scenarios": needs_revision_list,
            "rejected_scenarios": rejected_list,
            "report": report
        }
