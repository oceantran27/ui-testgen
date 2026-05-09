"""
Flow Discovery Service — Phase 8 implementation.
Builds UI flows and transitions from extracted UI states.
"""
import json
import uuid
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.flow import Flow
from app.db.models.flow_transition import FlowTransition
from app.db.models.ui_state import UIState
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service


def _generate_flow_id() -> str:
    return f"fl_{uuid.uuid4().hex[:12]}"

def _generate_transition_id() -> str:
    return f"tr_{uuid.uuid4().hex[:12]}"

def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


class FlowDiscoveryService:
    """
    Heuristic-based UI flow discovery.
    """

    @staticmethod
    async def run_discovery(
        db: AsyncSession, 
        run_id: str, 
        state_catalog: List[Dict[str, Any]], 
        input_level: str,
        coarse_flow_group_hints: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main entry point for Phase 8.
        """
        start_time = time.time()
        log_event("flow_discovery_started", run_id=run_id, input_level=input_level)

        if not state_catalog:
            return {"error": "NO_VALID_UI_STATES_FOR_FLOW_DISCOVERY"}

        # 1. State Pair Generation & Analysis
        # For MVP, we use a simple heuristic to find transitions
        
        detected_flows = []
        all_transitions = []
        
        if input_level == "Level 1":
            # Handle Level 1: Pseudo-flow
            state = state_catalog[0]
            flow_id = _generate_flow_id()
            flow = Flow(
                id=flow_id,
                run_id=run_id,
                name=f"Single State Flow ({state['page_type']})",
                flow_type="single_state_pseudo_flow",
                input_level=input_level,
                start_state_id=state["state_id"],
                ordered_state_ids_json={"ids": [state["state_id"]]},
                confidence=0.9,
                confidence_label="high",
                warnings_json={"warning_code": "single_state_flow", "message": "Only one UI state available."}
            )
            db.add(flow)
            detected_flows.append(flow_id)
            
        else:
            # Handle Level 2 & 3: Heuristic ordering
            # Simple heuristic: Group by coarse flow groups if available, 
            # otherwise group by page type sequence (login -> dashboard, etc)
            
            # Step A: Generate transition candidates
            candidates = []
            for i, from_s in enumerate(state_catalog):
                for j, to_s in enumerate(state_catalog):
                    if i == j: continue
                    
                    # Heuristic score for transition (S_i -> S_j)
                    score = 0.0
                    reason = ""
                    t_type = "unknown_transition"
                    
                    # 1. Feedback delta (Login page -> Login page with error)
                    if from_s["page_type"] == to_s["page_type"]:
                        # If the transition logic from Phase 7 saw a feedback change, high score
                        score = 0.8
                        t_type = "same_page_feedback"
                        reason = f"States have the same page type ({from_s['page_type']}) suggesting a feedback or state change."
                    
                    # 2. Known journey patterns (Simplified)
                    if from_s["page_type"] == "login_page" and to_s["page_type"] == "dashboard_page":
                        score = 0.9
                        t_type = "form_submission_success"
                        reason = "Login success transition to dashboard."
                    
                    if score >= settings.TRANSITION_ACCEPT_THRESHOLD:
                        candidates.append({
                            "from_state_id": from_s["state_id"],
                            "to_state_id": to_s["state_id"],
                            "score": score,
                            "type": t_type,
                            "reason": reason
                        })

            # Step B: Select best transitions and build flows
            # For MVP, we create one flow per coarse group hint or one linear flow
            if coarse_flow_group_hints:
                for idx, group in enumerate(coarse_flow_group_hints):
                    flow_id = _generate_flow_id()
                    group_state_ids = group["state_ids"]
                    
                    # Simple ordering within group based on score
                    # For MVP: we just use the order in catalog or simple heuristic
                    ordered_ids = group_state_ids # Placeholder ordering
                    
                    flow = Flow(
                        id=flow_id,
                        run_id=run_id,
                        name=group.get("group_hint", f"Flow {idx+1}"),
                        flow_type="linear_flow",
                        input_level=input_level,
                        start_state_id=ordered_ids[0],
                        ordered_state_ids_json={"ids": ordered_ids},
                        confidence=group.get("confidence", 0.7),
                        confidence_label="medium"
                    )
                    db.add(flow)
                    detected_flows.append(flow_id)
                    
                    # Add transitions for this flow
                    for cand in candidates:
                        if cand["from_state_id"] in group_state_ids and cand["to_state_id"] in group_state_ids:
                            trans = FlowTransition(
                                id=_generate_transition_id(),
                                run_id=run_id,
                                flow_id=flow_id,
                                from_state_id=cand["from_state_id"],
                                to_state_id=cand["to_state_id"],
                                transition_type=cand["type"],
                                score=cand["score"],
                                confidence_label="medium",
                                reason=cand["reason"]
                            )
                            db.add(trans)
                            all_transitions.append(trans.id)
            else:
                # No hints, create one big flow for all states (linear heuristic)
                flow_id = _generate_flow_id()
                all_ids = [s["state_id"] for s in state_catalog]
                
                flow = Flow(
                    id=flow_id,
                    run_id=run_id,
                    name="Auto-discovered Flow",
                    flow_type="linear_flow",
                    input_level=input_level,
                    start_state_id=all_ids[0],
                    ordered_state_ids_json={"ids": all_ids},
                    confidence=0.5,
                    confidence_label="low"
                )
                db.add(flow)
                detected_flows.append(flow_id)
                
                for cand in candidates:
                    trans = FlowTransition(
                        id=_generate_transition_id(),
                        run_id=run_id,
                        flow_id=flow_id,
                        from_state_id=cand["from_state_id"],
                        to_state_id=cand["to_state_id"],
                        transition_type=cand["type"],
                        score=cand["score"],
                        confidence_label="medium",
                        reason=cand["reason"]
                    )
                    db.add(trans)
                    all_transitions.append(trans.id)

        # 3. Persistence & Report
        await db.commit()
        
        report = {
            "run_id": run_id,
            "detected_input_level": input_level,
            "state_count": len(state_catalog),
            "detected_flow_count": len(detected_flows),
            "transition_count": len(all_transitions),
            "flow_ids": detected_flows,
            "metrics": {
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        }
        
        if settings.SAVE_FLOW_DISCOVERY_REPORT:
            report_bytes = json.dumps(report, indent=2).encode("utf-8")
            report_key = f"artifacts/{run_id}/flow_discovery/flow_discovery_report.json"
            report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

            artifact = Artifact(
                id=_generate_artifact_id(),
                run_id=run_id,
                artifact_type="flow_discovery_report",
                node_name="flow_discovery",
                storage_uri=report_uri,
                metadata_json={"flow_count": len(detected_flows)},
            )
            db.add(artifact)
            await db.commit()

        log_event("flow_discovery_completed", run_id=run_id, flow_count=len(detected_flows))
        
        # Build graph data for frontend
        ui_flow_graph = {
            "nodes": [{"id": s["state_id"], "page_type": s["page_type"]} for s in state_catalog],
            "edges": [] # Can be populated from candidates for visualization
        }

        return {
            "detected_flows": detected_flows,
            "ui_flow_graph": ui_flow_graph,
            "report": report
        }
