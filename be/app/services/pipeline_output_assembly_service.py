"""
Final pipeline output assembly — compiles graph state into final_output.json and metrics.
"""
import json
import time
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event
from app.services.storage_service import storage_service


def _exported_behaviour_scenarios(
    scenario_pkg: Dict[str, Any],
    validation_pkg: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], List[str]]:
    """Keep draft scenarios accepted by Agent 7 with allowed validation_status."""
    drafts = list(scenario_pkg.get("test_scenarios") or [])
    validated = list(validation_pkg.get("validated_scenarios") or [])
    allow = frozenset(
        (s or "").strip().lower()
        for s in (settings.PIPELINE_SCENARIO_EXPORT_VALIDATION_STATUSES or ["validated"])
    )

    verdict_by_id: Dict[str, Dict[str, Any]] = {}
    for row in validated:
        if isinstance(row, dict) and row.get("scenario_id"):
            verdict_by_id[str(row["scenario_id"])] = row

    exported: List[Dict[str, Any]] = []
    excluded: List[str] = []
    for d in drafts:
        if not isinstance(d, dict):
            continue
        sid = str(d.get("scenario_id") or "")
        verdict = verdict_by_id.get(sid)
        if not verdict:
            excluded.append(sid or "<missing_id>")
            continue
        status = str(verdict.get("validation_status") or "").lower()
        if status not in allow:
            excluded.append(sid)
            continue
        acc = verdict.get("acceptance_decision") or {}
        if not acc.get("include_in_final_output", True):
            excluded.append(sid)
            continue
        exported.append(d)

    return exported, excluded


async def run_pipeline_output_assembly(
    _db: AsyncSession,
    run_id: str,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Assembles final_output.json and calculates metrics from LangGraph PipelineState-shaped dict.
    """
    start_time = time.time()
    log_event("pipeline_output_assembly_started", run_id=run_id)

    screen_intent_pkg = state.get("screen_intent_package", {})
    intent_pkg = state.get("intent_package", {})
    scenario_pkg = state.get("scenario_draft_package", {})
    validation_pkg = state.get("validated_scenario_package", {})

    validation_report = validation_pkg.get("report")
    if not isinstance(validation_report, dict):
        validation_report = {}

    audit_suggestions_flat = state.get("audit_revision_suggestions") or []

    exported_scenarios, excluded_scenario_ids = _exported_behaviour_scenarios(scenario_pkg, validation_pkg)

    fdr = state.get("flow_discovery_result") or {}

    assembly_flow_method = (
        "global_compressed_batch"
        if fdr.get("discovery_engine") == "global_compressed_batch"
        else "intent_aware_structured_reasoning"
    )

    final_output = {
        "run_id": run_id,
        "system_version": "ui_testgen_pipeline_v2",
        "input_assumption": {
            "image_quality_validation": "skipped",
            "image_size_validation": "skipped",
            "reason": "controlled valid viewport screenshot input",
        },
        "duplicate_processing": {
            "canonical_state_count": len(state.get("state_catalog", [])),
        },
        "state_catalog": state.get("state_catalog", []),
        "flow_discovery": {
            "method": assembly_flow_method,
            "discovery_engine": fdr.get("discovery_engine"),
            "candidate_flows": fdr.get("candidate_flows", []),
            "warnings": fdr.get("discovery_warnings", []),
            "global_discovery_result_summary": (
                {
                    "flow_count": len(
                        (
                            (fdr.get("global_discovery_result") or {}).get("candidate_flows")
                            or (fdr.get("global_discovery_result") or {}).get("discovered_flows")
                            or []
                        )
                    )
                }
                if isinstance(fdr.get("global_discovery_result"), dict)
                else None
            ),
            "compressed_catalog_metrics": (
                (state.get("compressed_catalog_package") or {}).get("compression_stats")
                if isinstance(state.get("compressed_catalog_package"), dict)
                else None
            ),
        },
        "screen_behaviour_intents": screen_intent_pkg.get("screen_intent_catalog", []),
        "behaviour_contracts": intent_pkg.get("behaviour_intents", []),
        "behaviour_scenarios": exported_scenarios,
        "behaviour_scenarios_all_drafts": scenario_pkg.get("test_scenarios", []),
        "scenario_export_meta": {
            "validation_status_allowlist": settings.PIPELINE_SCENARIO_EXPORT_VALIDATION_STATUSES,
            "exported_count": len(exported_scenarios),
            "excluded_after_audit_count": len(excluded_scenario_ids),
            "excluded_scenario_ids": excluded_scenario_ids[:200],
        },
        "scenario_generation": {
            "mode": (scenario_pkg.get("report") or {}).get("mode", "deterministic_python"),
            "auto_revision_retry": False,
        },
        "validation": {
            "validated_scenarios": validation_pkg.get("validated_scenarios", []),
            "summary": validation_pkg.get("final_output_summary", {}),
            "audit_revision_suggestions": audit_suggestions_flat,
            "revision_suggestions_apply_mode": "manual_or_future_pipeline",
            "audit_pipeline_report": validation_report,
        },
        "metrics": _calculate_metrics(state),
        "system_warnings": state.get("warnings", []),
    }

    if settings.SAVE_PIPELINE_FINAL_OUTPUT:
        output_bytes = json.dumps(final_output, indent=2, default=str).encode("utf-8")
        output_key = f"artifacts/{run_id}/final_output.json"
        storage_service.upload_file(output_bytes, output_key, content_type="application/json")

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("pipeline_output_assembly_completed", run_id=run_id, duration_ms=duration_ms)

    return final_output


def _calculate_metrics(state: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate metrics for final_output."""
    unique_states = state.get("state_catalog", [])
    flow_discovery = state.get("flow_discovery_result", {})
    screen_intent_pkg = state.get("screen_intent_package", {})
    intent_pkg = state.get("intent_package", {})
    scenario_pkg = state.get("scenario_draft_package", {})
    validation_pkg = state.get("validated_scenario_package", {})

    validated_scenarios = validation_pkg.get("validated_scenarios", [])

    avg_grounding_score = 0.0
    if validated_scenarios:
        scores = [s.get("grounding_score", 0.0) for s in validated_scenarios if "grounding_score" in s]
        if scores:
            avg_grounding_score = sum(scores) / len(scores)

    exported_raw, excluded_ids = _exported_behaviour_scenarios(scenario_pkg, validation_pkg)

    cmp_pkg = state.get("compressed_catalog_package") or {}

    comp_stats = cmp_pkg.get("compression_stats") or {}
    gd_rep = flow_discovery.get("report") or {}

    return {
        "input_image_count": len(state.get("raw_image_ids", [])),
        "canonical_state_count": len(unique_states),
        "flow_count": len(flow_discovery.get("candidate_flows", [])),
        "screen_intent_count": len(screen_intent_pkg.get("screen_intent_catalog", [])),
        "behaviour_contract_count": len(intent_pkg.get("behaviour_intents", [])),
        "scenario_count": len(scenario_pkg.get("test_scenarios", [])),
        "scenario_export_count": len(exported_raw),
        "scenario_audit_excluded_count": len(excluded_ids),
        "compressed_catalog_screen_count": len(cmp_pkg.get("compressed_catalog") or []),
        "compressed_catalog_token_estimate_div4": comp_stats.get("token_estimate_div4"),
        "global_flow_discovery_catalog_char_len": gd_rep.get("global_discovery_input_catalog_char_len"),
        "validated_scenario_count": len(validated_scenarios),
        "avg_grounding_score": float(avg_grounding_score),
    }
