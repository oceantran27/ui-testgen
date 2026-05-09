"""
Scenario Curation Service — Phase 13 implementation.
Uses LLM to deduplicate, prioritize, and finalize the scenario set.
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

class CuratedScenarioOutput(BaseModel):
    scenario_id: str
    final_status: str = Field(..., description="'accepted', 'accepted_with_warning', 'needs_review', 'rejected', 'duplicate_removed'")
    final_priority: str = Field(..., description="'P0', 'P1', 'P2', 'P3'")
    priority_score: float = Field(..., ge=0.0, le=1.0)
    priority_reason: str
    curation_reason: str
    duplicate_group_id: Optional[str] = None
    is_canonical_scenario: bool = True
    final_confidence_adjustment: float = Field(..., description="Adjustment to apply to final_confidence (-0.5 to +0.5)")


class DuplicateGroupOutput(BaseModel):
    group_id: str
    canonical_id: str
    duplicate_ids: List[str]
    reason: str


class ScenarioCurationOutput(BaseModel):
    curated_scenarios: List[CuratedScenarioOutput]
    duplicate_groups: List[DuplicateGroupOutput]


# ──────────────────────────────────────────────
# Service Implementation
# ──────────────────────────────────────────────

def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


class ScenarioCurationService:
    """
    LLM-powered scenario curation and deduplication.
    """

    @staticmethod
    async def run_curation(db: AsyncSession, run_id: str, scenarios_to_curate: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main entry point for Phase 13 curation.
        """
        start_time = time.time()
        log_event("scenario_curation_started", run_id=run_id, input_count=len(scenarios_to_curate))

        if not scenarios_to_curate:
            return {"error": "NO_SCENARIOS_FOR_CURATION"}

        scenario_ids = [s["scenario_id"] for s in scenarios_to_curate]
        result = await db.execute(
            select(BehaviourScenario).where(BehaviourScenario.id.in_(scenario_ids))
        )
        scenarios = result.scalars().all()

        # 1. Build Curation Context
        scenario_list_for_llm = []
        for s in scenarios:
            scenario_list_for_llm.append({
                "id": s.id,
                "title": s.scenario_title,
                "type": s.scenario_type,
                "steps": s.structured_steps_json,
                "validation": {
                    "status": s.validation_status,
                    "score": s.grounding_score,
                    "issues": s.validation_issues_json.get("issues", []) if s.validation_issues_json else []
                }
            })

        context = {
            "run_id": run_id,
            "scenarios": scenario_list_for_llm
        }

        # 2. Call LLM for Curation
        try:
            system_instruction = (
                "You are a Principal Test Architect. Your task is to CURATE a final list of test scenarios. "
                "1. Identify duplicates: group scenarios that test the same thing even if the text differs. "
                "2. Choose the 'Canonical' scenario for each group (the one with best grounding/clarity). "
                "3. Assign priority (P0=Critical, P1=Core, P2=Normal, P3=Minor). "
                "4. Finalize status and adjust confidence based on the overall set quality."
            )
            user_instruction = (
                f"Curate the following list of scenarios.\n\n"
                f"Scenario List: {json.dumps(context, indent=2)}"
            )

            response = await model_adapter.call_text_structured(
                task_name="scenario_curation",
                run_id=run_id,
                node_name="scenario_curation",
                system_instruction=system_instruction,
                user_instruction=user_instruction,
                output_schema=ScenarioCurationOutput,
                prompt_name="scenario_curation_v1"
            )

            curation: ScenarioCurationOutput = response.parsed_output

            # 3. Apply Curation to Database
            curation_map = {cs.scenario_id: cs for cs in curation.curated_scenarios}
            
            final_scenarios_list = []
            
            for s in scenarios:
                cs = curation_map.get(s.id)
                if not cs:
                    continue
                
                s.final_status = cs.final_status
                s.final_priority = cs.final_priority
                s.priority_score = cs.priority_score
                s.priority_reason = cs.priority_reason
                s.curation_reason = cs.curation_reason
                s.duplicate_group_id = cs.duplicate_group_id
                s.is_canonical_scenario = cs.is_canonical_scenario
                s.curated_at = datetime.datetime.utcnow()
                
                # Adjust confidence
                s.final_confidence = max(0.0, min(1.0, s.final_confidence + cs.final_confidence_adjustment))
                
                if s.final_status in ["accepted", "accepted_with_warning"]:
                    final_scenarios_list.append({
                        "scenario_id": s.id,
                        "title": s.scenario_title,
                        "priority": s.final_priority,
                        "confidence": s.final_confidence,
                        "status": s.final_status
                    })

            await db.commit()

            # 4. Report
            report = {
                "run_id": run_id,
                "summary": {
                    "input_count": len(scenarios),
                    "accepted_count": len(final_scenarios_list),
                    "duplicate_groups_count": len(curation.duplicate_groups)
                },
                "duplicate_groups": [dg.model_dump() for dg in curation.duplicate_groups],
                "curated_results": [cs.model_dump() for cs in curation.curated_scenarios],
                "metrics": {
                    "duration_ms": int((time.time() - start_time) * 1000)
                }
            }

            if settings.SAVE_SCENARIO_CURATION_REPORT:
                report_bytes = json.dumps(report, indent=2).encode("utf-8")
                report_key = f"artifacts/{run_id}/scenario_curation/scenario_curation_report.json"
                report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

                artifact = Artifact(
                    id=_generate_artifact_id(),
                    run_id=run_id,
                    artifact_type="scenario_curation_report",
                    node_name="scenario_curation",
                    storage_uri=report_uri,
                )
                db.add(artifact)
                await db.commit()

            log_event("scenario_curation_completed", run_id=run_id, accepted=len(final_scenarios_list))

            return {
                "curated_scenarios": final_scenarios_list,
                "duplicate_groups": report["duplicate_groups"],
                "report": report
            }

        except Exception as e:
            logger.exception(f"Failed to curate scenarios for run {run_id}: {e}")
            return {"error": str(e)}
