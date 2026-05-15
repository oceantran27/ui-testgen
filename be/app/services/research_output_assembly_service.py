"""
Research Output Assembly Service — Phase Research v1.
Compiles all data into final_output.json and metrics.
"""
import time
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event
from app.services.storage_service import storage_service

async def run_research_output_assembly(
    db: AsyncSession, 
    run_id: str, 
    state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Assembles final_output.json and calculates metrics.
    """
    start_time = time.time()
    log_event("research_output_assembly_started", run_id=run_id)

    # 1. Gather all data from state
    intent_pkg = state.get("intent_package", {})
    scenario_pkg = state.get("scenario_draft_package", {})
    validation_pkg = state.get("validated_scenario_package", {})

    final_output = {
        "run_id": run_id,
        "system_version": "model_first_research_v2",
        "input_assumption": {
            "image_quality_validation": "skipped",
            "image_size_validation": "skipped",
            "reason": "controlled valid viewport screenshot input"
        },
        "duplicate_processing": {
            "exact_duplicate_groups": state.get("exact_duplicate_groups", []),
            "canonical_state_count": len(state.get("state_catalog", []))
        },
        "state_catalog": state.get("state_catalog", []),
        "flow_discovery": {
            "method": "llm_structured_reasoning",
            "candidate_flows": state.get("flow_discovery_result", {}).get("candidate_flows", []),
            "warnings": state.get("flow_discovery_result", {}).get("discovery_warnings", [])
        },
        "behaviour_intents": intent_pkg.get("behaviour_intents", []),
        "behaviour_scenarios": scenario_pkg.get("test_scenarios", []),
        "validation": {
            "validated_scenarios": validation_pkg.get("validated_scenarios", []),
            "summary": validation_pkg.get("final_output_summary", {})
        },
        "metrics": _calculate_metrics(state),
        "system_warnings": state.get("warnings", [])
    }

    # 2. Save to storage
    if settings.SAVE_RESEARCH_FINAL_OUTPUT:
        output_bytes = json.dumps(final_output, indent=2, default=str).encode("utf-8")
        output_key = f"artifacts/{run_id}/final_output.json"
        storage_service.upload_file(output_bytes, output_key, content_type="application/json")

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("research_output_assembly_completed", run_id=run_id, duration_ms=duration_ms)

    return final_output

def _calculate_metrics(state: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate research metrics."""
    unique_states = state.get("state_catalog", [])
    flow_discovery = state.get("flow_discovery_result", {})
    intent_pkg = state.get("intent_package", {})
    scenario_pkg = state.get("scenario_draft_package", {})
    validation_pkg = state.get("validated_scenario_package", {})
    
    validated_scenarios = validation_pkg.get("validated_scenarios", [])
    
    # Simple averages
    avg_grounding_score = 0.0
    if validated_scenarios:
        scores = [s.get("grounding_score", 0.0) for s in validated_scenarios if "grounding_score" in s]
        if scores:
            avg_grounding_score = sum(scores) / len(scores)

    return {
        "input_image_count": len(state.get("raw_image_ids", [])),
        "exact_duplicate_group_count": len(state.get("exact_duplicate_groups", [])),
        "canonical_state_count": len(unique_states),
        "flow_count": len(flow_discovery.get("candidate_flows", [])),
        "intent_count": len(intent_pkg.get("behaviour_intents", [])),
        "scenario_count": len(scenario_pkg.get("test_scenarios", [])),
        "validated_scenario_count": len(validated_scenarios),
        "average_grounding_score": avg_grounding_score,
    }
