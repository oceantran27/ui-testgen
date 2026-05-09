"""
Behaviour Scenario Generation Service — Phase 11 implementation.
Uses LLM (GPT-4o-mini) to generate draft Gherkin and structured JSON test scenarios.
"""
import json
import uuid
import time
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.behaviour_intent import BehaviourIntent
from app.db.models.behaviour_scenario import BehaviourScenario
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service
from app.model_providers.registry import model_adapter


# ──────────────────────────────────────────────
# Pydantic Schemas for LLM Output
# ──────────────────────────────────────────────

class ScenarioStepOutput(BaseModel):
    step_type: str = Field(..., description="The step type: 'given', 'when', or 'then'.")
    text: str = Field(..., description="The Gherkin step text.")
    evidence_state_ids: List[str] = Field(default_factory=list, description="IDs of the UI states that provide evidence for this step.")
    evidence_element_ids: List[str] = Field(default_factory=list, description="IDs of UI elements involved in this step.")
    inference_level: str = Field(..., description="How much inference was used: 'grounded', 'partially_inferred', or 'inferred_only'.")


class StructuredScenarioOutput(BaseModel):
    feature: str = Field(..., description="The BDD Feature name.")
    title: str = Field(..., description="The BDD Scenario title.")
    scenario_type: str = Field(..., description="Category: 'positive_behaviour', 'negative_behaviour', etc.")
    given: List[ScenarioStepOutput] = Field(..., description="List of Given steps.")
    when: List[ScenarioStepOutput] = Field(..., description="List of When steps.")
    then: List[ScenarioStepOutput] = Field(..., description="List of Then steps.")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions made by the LLM.")
    warnings: List[str] = Field(default_factory=list, description="Warnings regarding the generated scenario.")
    initial_confidence: float = Field(..., ge=0.0, le=1.0, description="Initial confidence score.")


# ──────────────────────────────────────────────
# Service Implementation
# ──────────────────────────────────────────────

def _generate_scenario_id() -> str:
    return f"bts_{uuid.uuid4().hex[:12]}"

def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


class ScenarioGenerationService:
    """
    LLM-powered behaviour scenario generation.
    """

    @staticmethod
    async def run_generation(db: AsyncSession, run_id: str, behaviour_intents: List[Dict[str, Any]], state_catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main entry point for Phase 11 generation.
        """
        start_time = time.time()
        log_event("behaviour_scenario_generation_started", run_id=run_id, intent_count=len(behaviour_intents))

        if not behaviour_intents:
            return {"error": "NO_GENERATABLE_BEHAVIOUR_INTENTS"}

        # 1. Load Intent objects from DB to get full evidence context if needed
        # (Assuming behaviour_intents passed in contain basic IDs)
        intent_ids = [bi["intent_id"] for bi in behaviour_intents]
        result = await db.execute(
            select(BehaviourIntent).where(BehaviourIntent.id.in_(intent_ids))
        )
        intents = result.scalars().all()
        
        all_draft_scenarios = []
        
        for intent in intents:
            if not intent.should_generate:
                continue

            log_event("generating_scenario_for_intent", intent_id=intent.id)
            
            # 2. Build Context for LLM
            # Load associated flow to get state sequence
            from app.db.models.flow import Flow
            flow_result = await db.execute(select(Flow).where(Flow.id == intent.flow_id))
            flow = flow_result.scalar_one_or_none()
            
            if not flow:
                logger.warning(f"Flow {intent.flow_id} not found for intent {intent.id}")
                continue

            # Extract state details for the prompt
            flow_states = []
            ordered_ids = flow.ordered_state_ids_json.get("ids", [])
            for sid in ordered_ids:
                state_data = next((s for s in state_catalog if s["state_id"] == sid), None)
                if state_data:
                    flow_states.append({
                        "id": sid,
                        "page_type": state_data.get("page_type"),
                        "summary": state_data.get("state_summary"),
                        "elements": state_data.get("actionable_elements", []) + state_data.get("feedback_elements", [])
                    })

            context = {
                "intent_name": intent.intent_name,
                "user_goal": intent.user_goal,
                "domain": intent.behaviour_domain,
                "outcome": intent.behaviour_outcome,
                "hint": intent.scenario_type_hint,
                "expected_grounding": intent.expected_grounding,
                "flow_states": flow_states,
                "warnings": intent.warnings_json
            }

            # 3. Call LLM
            try:
                system_instruction = (
                    "You are a World-Class BDD Expert and QA Automation Engineer. "
                    "Your task is to generate a draft Gherkin behaviour test scenario based on the provided user intent and UI flow. "
                    "Return the scenario in a structured JSON format. "
                    "For each step, you MUST map it to the evidence IDs (state_id or element_id) from the provided context. "
                    "Be descriptive but concise. Avoid hallucinating elements or data not mentioned in the context."
                )
                user_instruction = (
                    f"Generate a BDD behaviour test scenario for the following intent context.\n\n"
                    f"Intent Context: {json.dumps(context, indent=2)}"
                )

                response = await model_adapter.call_text_structured(
                    task_name="behaviour_scenario_generation",
                    run_id=run_id,
                    node_name="behaviour_scenario_generation",
                    system_instruction=system_instruction,
                    user_instruction=user_instruction,
                    output_schema=StructuredScenarioOutput,
                    prompt_name="behaviour_scenario_generation_v1"
                )

                parsed_output: StructuredScenarioOutput = response.parsed_output
                
                # 4. Generate Gherkin Text
                gherkin = f"Feature: {parsed_output.feature}\n\n"
                gherkin += f"  Scenario: {parsed_output.title}\n"
                for step in parsed_output.given:
                    gherkin += f"    Given {step.text}\n"
                for step in parsed_output.when:
                    gherkin += f"    When {step.text}\n"
                for step in parsed_output.then:
                    gherkin += f"    Then {step.text}\n"

                # 5. Save to Database
                scenario_id = _generate_scenario_id()
                confidence_label = "high" if parsed_output.initial_confidence >= 0.8 else "medium" if parsed_output.initial_confidence >= 0.5 else "low"
                
                bs = BehaviourScenario(
                    id=scenario_id,
                    run_id=run_id,
                    flow_id=intent.flow_id,
                    intent_id=intent.id,
                    feature=parsed_output.feature,
                    scenario_title=parsed_output.title,
                    scenario_type=parsed_output.scenario_type,
                    grounding_mode=intent.expected_grounding,
                    gherkin_text=gherkin,
                    structured_steps_json={
                        "given": [s.model_dump() for s in parsed_output.given],
                        "when": [s.model_dump() for s in parsed_output.when],
                        "then": [s.model_dump() for s in parsed_output.then]
                    },
                    evidence_json={"state_ids": ordered_ids},
                    assumptions_json={"assumptions": parsed_output.assumptions},
                    warnings_json={"warnings": parsed_output.warnings},
                    initial_confidence=parsed_output.initial_confidence,
                    confidence_label=confidence_label,
                    status="draft"
                )
                db.add(bs)
                
                all_draft_scenarios.append({
                    "scenario_id": scenario_id,
                    "intent_id": intent.id,
                    "title": bs.scenario_title,
                    "confidence": bs.initial_confidence,
                    "status": bs.status
                })

            except Exception as e:
                logger.exception(f"Failed to generate scenario for intent {intent.id}: {e}")

        # 6. Report and Persistence
        await db.commit()
        
        report = {
            "run_id": run_id,
            "intent_count": len(behaviour_intents),
            "generated_scenario_count": len(all_draft_scenarios),
            "scenarios": all_draft_scenarios,
            "metrics": {
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        }
        
        if settings.SAVE_SCENARIO_GENERATION_REPORT:
            report_bytes = json.dumps(report, indent=2).encode("utf-8")
            report_key = f"artifacts/{run_id}/scenario_generation/behaviour_scenario_generation_report.json"
            report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

            artifact = Artifact(
                id=_generate_artifact_id(),
                run_id=run_id,
                artifact_type="behaviour_scenario_generation_report",
                node_name="behaviour_scenario_generation",
                storage_uri=report_uri,
            )
            db.add(artifact)
            await db.commit()

        log_event("behaviour_scenario_generation_completed", run_id=run_id, scenario_count=len(all_draft_scenarios))
        
        return {
            "draft_scenarios": all_draft_scenarios,
            "report": report
        }
