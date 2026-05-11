"""
Behaviour Intent Inference Service — Phase 10 implementation.
Uses LLM (GPT-4o-mini) to infer user intentions and goals from UI flows.
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
from app.db.models.flow import Flow
from app.db.models.behaviour_intent import BehaviourIntent
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service
from app.model_providers.registry import model_adapter


# ──────────────────────────────────────────────
# Pydantic Schemas for LLM Output
# ──────────────────────────────────────────────

class IntentOutput(BaseModel):
    intent_name: str = Field(..., description="Machine-readable name of the intent, e.g., 'login_failed', 'add_to_cart'.")
    behaviour_domain: str = Field(..., description="The functional area, e.g., 'authentication', 'cart', 'navigation'.")
    behaviour_outcome: str = Field(..., description="The result type, e.g., 'success', 'failure', 'validation_error'.")
    user_goal: str = Field(..., description="A natural language description of what the user is trying to achieve.")
    scenario_type_hint: str = Field(..., description="Suggestion for Phase 11: 'positive_behaviour', 'negative_behaviour', etc.")
    expected_grounding: str = Field(..., description="How much evidence exists: 'grounded', 'partially_inferred', 'inferred_only'.")
    should_generate: bool = Field(True, description="Whether Phase 11 should generate a test scenario for this intent.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score for this inference.")
    reason: str = Field(..., description="Brief explanation for the chosen intent and confidence.")


class FlowIntentInferenceOutput(BaseModel):
    intents: List[IntentOutput] = Field(..., description="List of inferred intents for the flow (usually one, but more if branched).")


# ──────────────────────────────────────────────
# Service Implementation
# ──────────────────────────────────────────────

def _generate_intent_id() -> str:
    return f"bi_{uuid.uuid4().hex[:12]}"

def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


def _flow_db_id(flow: Dict[str, Any]) -> Optional[str]:
    fid = flow.get("flow_id")
    if fid and isinstance(fid, str):
        return fid
    return None


class BehaviourIntentService:
    """
    LLM-powered behaviour intent inference.
    """

    @staticmethod
    async def run_inference(db: AsyncSession, run_id: str, flow_clusters: List[Dict[str, Any]], state_catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main entry point for Phase 10 inference.
        """
        start_time = time.time()
        log_event("behaviour_intent_inference_started", run_id=run_id, flow_count=len(flow_clusters))

        if not flow_clusters:
            return {"error": "NO_USABLE_FLOWS_FOR_INTENT_INFERENCE"}

        all_inferred_intents = []
        
        for flow in flow_clusters:
            if flow.get("scenario_generation_mode") == "do_not_generate":
                logger.info(f"Skipping flow {flow.get('flow_name')} as it is marked do_not_generate")
                continue

            fid_for_row = _flow_db_id(flow)
            if not fid_for_row:
                logger.warning(
                    "Skipping intent inference for flow %r: missing flow_id (persist Flow rows before Phase 10).",
                    flow.get("flow_name"),
                )
                continue

            log_event("inferring_intent_for_flow", flow_name=flow.get("flow_name"))
            
            # 2. Build Context for LLM
            flow_context = {
                "flow_name": flow.get("flow_name"),
                "flow_type": flow.get("flow_type"),
                "ordered_state_ids": flow.get("ordered_state_ids", []),
                "transitions": flow.get("transitions", []),
                "behaviour_hint": flow.get("behaviour_hint", ""),
                "completeness_status": flow.get("completeness_status"),
                "scenario_generation_mode": flow.get("scenario_generation_mode"),
                "states": [
                    {
                        "id": s["state_id"],
                        "page_type": s["page_type"],
                        "summary": s.get("state_summary", ""),
                        "has_feedback": s.get("has_feedback", False),
                        "feedback_elements": s.get("feedback_elements", [])
                    }
                    for s in state_catalog if s["state_id"] in flow.get("ordered_state_ids", [])
                ],
                "flow_reason": flow.get("reason", ""),
                "flow_warnings": flow.get("warnings", [])
            }

            # 3. Call LLM
            try:
                system_instruction = (
                    "You are a Senior QA Automation Architect and UX Analyst. "
                    "Your task is to infer the user's 'Behaviour Intent' from a sequence of UI states (a flow). "
                    "Determine what functional domain the flow belongs to, what the outcome is, and what the user's specific goal is. "
                    "Use machine-readable intent names like 'login_success', 'search_no_results', etc."
                )
                user_instruction = (
                    f"Analyze the following UI flow context and return the inferred behaviour intents in structured JSON format.\n\n"
                    f"Flow Context: {json.dumps(flow_context, indent=2)}"
                )

                response = await model_adapter.call_text_structured(
                    task_name="behaviour_intent_inference",
                    run_id=run_id,
                    node_name="behaviour_intent_inference",
                    system_instruction=system_instruction,
                    user_instruction=user_instruction,
                    output_schema=FlowIntentInferenceOutput,
                    provider_override=settings.BEHAVIOUR_INTENT_MODEL_PROVIDER,
                    model_name_override=settings.BEHAVIOUR_INTENT_MODEL_NAME,
                    prompt_name="behaviour_intent_inference_v1"
                )

                parsed_output: FlowIntentInferenceOutput = response.parsed_output
                
                # 4. Process and Save Intents
                for intent_data in parsed_output.intents:
                    intent_id = _generate_intent_id()
                    confidence_label = "high" if intent_data.confidence >= 0.8 else "medium" if intent_data.confidence >= 0.5 else "low"
                    
                    bi = BehaviourIntent(
                        id=intent_id,
                        run_id=run_id,
                        flow_id=fid_for_row,
                        intent_name=intent_data.intent_name,
                        behaviour_domain=intent_data.behaviour_domain,
                        behaviour_outcome=intent_data.behaviour_outcome,
                        user_goal=intent_data.user_goal,
                        scenario_type_hint=intent_data.scenario_type_hint,
                        expected_grounding=intent_data.expected_grounding,
                        should_generate=intent_data.should_generate,
                        confidence=intent_data.confidence,
                        confidence_label=confidence_label,
                        evidence_state_ids_json={"ids": flow.get("ordered_state_ids", [])},
                        raw_result_json=intent_data.model_dump()
                    )
                    db.add(bi)
                    
                    all_inferred_intents.append({
                        "intent_id": intent_id,
                        "flow_id": fid_for_row,
                        "flow_name": flow.get("flow_name"),
                        "intent_name": bi.intent_name,
                        "domain": bi.behaviour_domain,
                        "goal": bi.user_goal,
                        "confidence": bi.confidence,
                        "scenario_type_hint": bi.scenario_type_hint,
                        "expected_grounding": bi.expected_grounding
                    })

            except Exception as e:
                logger.exception(f"Failed to infer intent for flow {flow.get('flow_name')}: {e}")
                intent_id = _generate_intent_id()
                bi = BehaviourIntent(
                    id=intent_id,
                    run_id=run_id,
                    flow_id=fid_for_row,
                    intent_name="unknown_behaviour",
                    behaviour_domain="unknown",
                    behaviour_outcome="unknown",
                    user_goal="Unknown user goal due to processing error.",
                    scenario_type_hint="unknown",
                    expected_grounding="needs_review",
                    should_generate=False,
                    confidence=0.0,
                    warnings_json={"error": str(e)}
                )
                db.add(bi)

        # 5. Report and Persistence
        await db.commit()
        
        report = {
            "run_id": run_id,
            "intent_count": len(all_inferred_intents),
            "intents": all_inferred_intents,
            "metrics": {
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        }
        
        if settings.SAVE_BEHAVIOUR_INTENT_REPORT:
            report_bytes = json.dumps(report, indent=2).encode("utf-8")
            report_key = f"artifacts/{run_id}/behaviour_intent/behaviour_intent_report.json"
            report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

            artifact = Artifact(
                id=_generate_artifact_id(),
                run_id=run_id,
                artifact_type="behaviour_intent_report",
                node_name="behaviour_intent_inference",
                storage_uri=report_uri,
            )
            db.add(artifact)
            await db.commit()

        log_event("behaviour_intent_inference_completed", run_id=run_id, intent_count=len(all_inferred_intents))
        
        return {
            "behaviour_intents": all_inferred_intents,
            "report": report
        }
