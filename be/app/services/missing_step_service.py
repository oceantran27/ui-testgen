"""
Missing Step Analysis Service — Phase 9 implementation.
Evaluates flow completeness and assigns penalties/eligibility.
"""
import json
import uuid
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.flow import Flow
from app.db.models.flow_transition import FlowTransition
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service


def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


class MissingStepService:
    """
    Heuristic-based missing step analyzer.
    """

    @staticmethod
    async def run_analysis(db: AsyncSession, run_id: str, flow_ids: List[str], state_catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main entry point for Phase 9 analysis.
        """
        start_time = time.time()
        log_event("missing_step_analysis_started", run_id=run_id, flow_count=len(flow_ids))

        if not flow_ids:
            return {"error": "NO_DETECTED_FLOWS_FOR_MISSING_STEP_ANALYSIS"}

        # 1. Load Flows and Transitions
        result = await db.execute(
            select(Flow).where(Flow.id.in_(flow_ids))
        )
        flows = result.scalars().all()
        
        flow_results = []
        
        for flow in flows:
            log_event("analyzing_flow_completeness", flow_id=flow.id)
            
            # Heuristics
            missing_items = []
            status = "complete"
            eligibility = "can_generate_grounded_scenario"
            penalty = 0.0
            warnings = []
            
            state_ids = flow.ordered_state_ids_json.get("ids", [])
            
            # Helper to get state metadata
            flow_states = [s for s in state_catalog if s["state_id"] in state_ids]
            
            # 1. Level 1 handling
            if flow.flow_type == "single_state_pseudo_flow":
                status = "single_state_inferred"
                eligibility = "can_generate_inferred_scenario_only"
                penalty = 0.2 # Small base penalty for single state
                warnings.append("Flow contains only one state; behaviour must be inferred.")
            else:
                # 2. Check Initial State
                first_state = next((s for s in flow_states if s["state_id"] == flow.start_state_id), None)
                if first_state:
                     # If first state looks like a result (feedback/dashboard) without preceding context
                     if first_state["page_type"] in ["dashboard_page", "success_page"] and not first_state.get("has_form", False):
                         missing_items.append({
                             "type": "missing_initial_state",
                             "severity": "high",
                             "reason": f"Flow starts with {first_state['page_type']} which is likely a result state."
                         })
                         penalty += settings.HIGH_MISSING_STEP_PENALTY

                # 3. Check Final Verification State
                last_state_id = state_ids[-1]
                last_state = next((s for s in flow_states if s["state_id"] == last_state_id), None)
                if last_state:
                    # If last state is just a form without feedback/result
                    if last_state.get("has_form", False) and not last_state.get("has_feedback", False):
                        missing_items.append({
                             "type": "missing_final_verification_state",
                             "severity": "critical",
                             "reason": "Flow ends on a form state without visible feedback or success confirmation."
                         })
                        penalty += settings.CRITICAL_MISSING_STEP_PENALTY
                        eligibility = "can_generate_inferred_scenario_only"

            # 4. Finalize Scoring
            penalty = min(penalty, settings.MAX_MISSING_STEP_TOTAL_PENALTY)
            adjusted_confidence = max(0.0, flow.confidence - penalty)
            
            if penalty >= 0.4:
                status = "partially_complete"
            if adjusted_confidence < settings.MIN_USABLE_FLOW_CONFIDENCE_AFTER_PENALTY:
                eligibility = "can_generate_inferred_scenario_only"
                
            # 5. Update DB
            flow.completeness_status = status
            flow.scenario_eligibility = eligibility
            flow.missing_step_penalty = penalty
            flow.adjusted_confidence = adjusted_confidence
            flow.missing_step_warnings_json = {"warnings": warnings, "items": missing_items}
            
            flow_results.append({
                "flow_id": flow.id,
                "status": status,
                "eligibility": eligibility,
                "penalty": penalty,
                "adjusted_confidence": adjusted_confidence,
                "missing_steps": missing_items
            })

        # 6. Report and Persistence
        await db.commit()
        
        report = {
            "run_id": run_id,
            "flow_results": flow_results,
            "summary": {
                "total_flows": len(flow_results),
                "complete": len([f for f in flow_results if f["status"] == "complete"]),
                "partially_complete": len([f for f in flow_results if f["status"] == "partially_complete"]),
                "inferred_only": len([f for f in flow_results if f["eligibility"] == "can_generate_inferred_scenario_only"])
            },
            "metrics": {
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        }
        
        if settings.SAVE_MISSING_STEP_ANALYSIS_REPORT:
            report_bytes = json.dumps(report, indent=2).encode("utf-8")
            report_key = f"artifacts/{run_id}/missing_step_analysis/missing_step_analysis_report.json"
            report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

            artifact = Artifact(
                id=_generate_artifact_id(),
                run_id=run_id,
                artifact_type="missing_step_analysis_report",
                node_name="missing_step_analysis",
                storage_uri=report_uri,
                metadata_json={"complete_flows": report["summary"]["complete"]},
            )
            db.add(artifact)
            await db.commit()

        log_event("missing_step_analysis_completed", run_id=run_id)
        
        return {
            "missing_step_report": report,
            "flow_completeness_results": flow_results
        }
