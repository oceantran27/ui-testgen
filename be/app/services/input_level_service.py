"""
Input Level Detection Service — Phase 7 implementation.
Classifies input into Level 1, 2, or 3 based on UI state analysis.
"""
import json
import uuid
from typing import Any, Dict, List, Optional
import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.run import Run
from app.db.models.ui_state import UIState
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service


def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


class InputLevelService:
    """
    Heuristic-based input level detection.
    """

    @staticmethod
    async def run_detection(db: AsyncSession, run_id: str, state_catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main entry point for Phase 7 detection.
        """
        start_time = time.time()
        log_event("input_level_detection_started", run_id=run_id)

        # 1. Load/Validate states
        if not state_catalog:
            # Try loading from DB if missing in state
            result = await db.execute(select(UIState).where(UIState.run_id == run_id))
            states = result.scalars().all()
            if not states:
                 log_event("input_level_detection_failed", run_id=run_id, reason="NO_VALID_UI_STATES")
                 return {"error": "NO_VALID_UI_STATES"}
            
            # Map back to catalog-like list
            state_catalog = [
                {
                    "state_id": s.id,
                    "page_type": s.page_type,
                    "state_signature": s.state_signature,
                    "confidence": s.confidence,
                }
                for s in states if s.extraction_status == "success"
            ]

        if not state_catalog:
            return {"error": "NO_VALID_UI_STATES"}

        # 2. Analyzers
        state_count = len(state_catalog)
        page_types = [s["page_type"] for s in state_catalog]
        distinct_page_types = list(set(page_types))
        
        # Diversity analysis
        page_type_count = len(distinct_page_types)
        
        # Basic Classifier
        detected_level = "Level 2"
        confidence = 0.8
        reason = "Multiple states detected."
        warnings = []
        coarse_groups = []

        if state_count == 1:
            detected_level = "Level 1"
            confidence = state_catalog[0].get("confidence", 0.9)
            reason = "Only one UI state is available."
            warnings.append({
                "warning_code": "single_state_inferred_only",
                "message": "Only one UI state is available. Behaviour scenarios will be inferred from visible UI elements.",
                "severity": "medium"
            })
            coarse_groups = [{
                "group_id": "G1",
                "state_ids": [state_catalog[0]["state_id"]],
                "group_hint": "single_state",
                "confidence": 1.0
            }]
        else:
            # Level 2 vs Level 3 Logic (Coarse)
            # Grouping based on page type distribution
            page_type_map: Dict[str, List[str]] = {}
            for s in state_catalog:
                pt = s["page_type"]
                if pt not in page_type_map:
                    page_type_map[pt] = []
                page_type_map[pt].append(s["state_id"])
            
            # Create coarse flow group hints
            # For MVP, we group states together if they have common flow patterns
            # e.g. login, dashboard, checkout sequences
            
            # Simplified diversity score
            diversity_score = page_type_count / state_count if state_count > 0 else 0
            
            if diversity_score > settings.LEVEL3_GROUP_SEPARATION_THRESHOLD or page_type_count > 3:
                detected_level = "Level 3"
                confidence = min(0.9, diversity_score + 0.2)
                reason = "Multiple distinct page types and states suggest multiple flows."
            else:
                detected_level = "Level 2"
                confidence = max(0.6, 1.0 - diversity_score)
                reason = "States appear to belong to related user journeys."

            # Generate group hints (coarse)
            for idx, pt in enumerate(distinct_page_types):
                coarse_groups.append({
                    "group_id": f"G{idx+1}",
                    "state_ids": page_type_map[pt],
                    "group_hint": f"{pt}_related_states",
                    "confidence": 0.8
                })

        # 3. Persistence
        await db.execute(
            update(Run).where(Run.id == run_id).values(
                input_level=detected_level,
                input_level_confidence=confidence,
                input_level_reason=reason
            )
        )
        
        # 4. Report Building
        report = {
            "run_id": run_id,
            "state_count": state_count,
            "detected_input_level": detected_level,
            "confidence": confidence,
            "reason": reason,
            "page_type_distribution": {pt: len(page_type_map.get(pt, [])) for pt in distinct_page_types} if state_count > 1 else {state_catalog[0]["page_type"]: 1},
            "coarse_flow_group_hints": coarse_groups,
            "warnings": warnings,
            "metrics": {
                "duration_ms": int((time.time() - start_time) * 1000)
            }
        }
        
        if settings.SAVE_INPUT_LEVEL_DETECTION_REPORT:
            report_bytes = json.dumps(report, indent=2).encode("utf-8")
            report_key = f"artifacts/{run_id}/input_level_detection/input_level_detection_report.json"
            report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

            artifact = Artifact(
                id=_generate_artifact_id(),
                run_id=run_id,
                artifact_type="input_level_detection_report",
                node_name="input_level_detection",
                storage_uri=report_uri,
                metadata_json={"detected_input_level": detected_level},
            )
            db.add(artifact)

        await db.commit()
        log_event("input_level_detection_completed", run_id=run_id, level=detected_level)
        
        return {
            "detected_input_level": detected_level,
            "input_level_confidence": confidence,
            "coarse_flow_group_hints": coarse_groups,
            "report": report,
            "warnings": warnings
        }
