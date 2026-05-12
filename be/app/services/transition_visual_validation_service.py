"""
Transition Visual Validation Service — Agent 4.
Verifies transitions using visual delta analysis (structured LLM output).
"""
import json
import time
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.ui_state import UIState
from app.model_providers import model_adapter
from app.model_providers.schemas import TransitionVisualValidationResult
from app.services.json_report_artifact import save_json_report_artifact

_TRANSITION_ARTIFACT = "transition_visual_validation_report"
_TRANSITION_SUBPATH = "transitions/transition_visual_validation_report.json"


async def _persist_transition_report(db: AsyncSession, run_id: str, payload: Dict[str, Any]) -> None:
    await save_json_report_artifact(
        db,
        run_id=run_id,
        artifact_type=_TRANSITION_ARTIFACT,
        node_name="transition_visual_validation_node",
        storage_subpath=_TRANSITION_SUBPATH,
        payload=payload,
    )
    await db.commit()


def _lookup_from_canonical_set(canonical_state_set: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    if not canonical_state_set:
        return {}
    out: Dict[str, List[str]] = {}
    for cs in canonical_state_set.get("canonical_states") or []:
        cid = cs.get("canonical_state_id")
        imgs = cs.get("source_image_ids") or []
        if cid and imgs:
            out[cid] = list(imgs)
    return out


async def _enrich_lookup_with_db(
    db: AsyncSession,
    run_id: str,
    needed_ids: Set[str],
    lookup: Dict[str, List[str]],
) -> None:
    """Fill missing canonical_state_id → image_ids from ui_states rows."""
    missing = [cid for cid in needed_ids if cid not in lookup or not lookup[cid]]
    if not missing:
        return
    res = await db.execute(
        select(UIState).where(UIState.run_id == run_id, UIState.canonical_id.in_(missing))
    )
    rows = list(res.scalars().all())
    bucket: Dict[str, List[str]] = {cid: [] for cid in missing}
    for row in rows:
        if row.canonical_id and row.image_id:
            bucket.setdefault(row.canonical_id, []).append(row.image_id)
    for cid, imgs in bucket.items():
        if imgs:
            lookup[cid] = sorted(set(imgs))


async def run_transition_visual_validation(
    db: AsyncSession,
    run_id: str,
    flow_discovery_result: Dict[str, Any],
    canonical_state_set: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("transition_visual_validation_started", run_id=run_id)

    if not flow_discovery_result or not flow_discovery_result.get("flows"):
        empty = TransitionVisualValidationResult(
            validated_flow_package_id="",
            source_flow_discovery_result_id="",
            validated_flows=[],
            package_warnings=["NO_FLOWS_TO_VALIDATE"],
        ).model_dump()
        await _persist_transition_report(db, run_id, empty)
        return empty

    needed_state_ids: Set[str] = set()
    for flow in flow_discovery_result["flows"]:
        for sid in flow.get("state_ids") or []:
            needed_state_ids.add(sid)
        for tr in flow.get("transitions") or []:
            needed_state_ids.add(tr.get("from_state_id"))
            needed_state_ids.add(tr.get("to_state_id"))

    canonical_state_image_lookup = _lookup_from_canonical_set(canonical_state_set)
    needed_ids_clean = {x for x in needed_state_ids if x}
    await _enrich_lookup_with_db(db, run_id, needed_ids_clean, canonical_state_image_lookup)

    system_instruction = prompt_manager.get_prompt("transition_visual_validation")

    user_payload = {
        "flow_discovery_result": {
            "flow_discovery_result_id": flow_discovery_result.get("flow_discovery_result_id"),
            "source_canonical_state_set_id": flow_discovery_result.get(
                "source_canonical_state_set_id"
            ),
            "flows": flow_discovery_result.get("flows"),
            "unassigned_state_ids": flow_discovery_result.get("unassigned_state_ids", []),
            "discovery_warnings": flow_discovery_result.get("discovery_warnings", []),
        },
        "canonical_state_image_lookup": canonical_state_image_lookup,
    }
    user_instruction = (
        "Validate each transition visually using the discovery result and image lookup.\n"
        f"{json.dumps(user_payload, indent=2)}"
    )

    response = await model_adapter.call_text_structured(
        task_name="transition_visual_validation",
        run_id=run_id,
        node_name="transition_visual_validation_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=TransitionVisualValidationResult,
        prompt_name="transition_visual_validation_prompt",
        prompt_version="v1",
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Transition Visual Validation failed: {response.error}")
        failed = TransitionVisualValidationResult(
            validated_flow_package_id="",
            source_flow_discovery_result_id=flow_discovery_result.get(
                "flow_discovery_result_id", ""
            ),
            validated_flows=[],
            package_warnings=[str(response.error or "LLM_FAILED")],
        ).model_dump()
        await _persist_transition_report(db, run_id, failed)
        return failed

    result: TransitionVisualValidationResult = response.parsed_output

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("transition_visual_validation_completed", run_id=run_id, duration_ms=duration_ms)

    dumped = result.model_dump()
    await _persist_transition_report(db, run_id, dumped)
    return dumped
