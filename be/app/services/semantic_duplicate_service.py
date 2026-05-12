"""
Semantic Canonicalization Service — Agent 2.
Gathers equivalent UI states into canonical representations.
"""
import json
import time
from typing import Any, Dict, List

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.ui_state import UIState
from app.model_providers import model_adapter
from app.model_providers.schemas import SemanticCanonicalizationResult
from app.services.json_report_artifact import save_json_report_artifact

_SEMANTIC_REPORT_ARTIFACT = "semantic_canonicalization_report"
_SEMANTIC_REPORT_SUBPATH = "semantic/semantic_canonicalization_report.json"


async def _persist_semantic_report(db: AsyncSession, run_id: str, payload: Dict[str, Any]) -> None:
    await save_json_report_artifact(
        db,
        run_id=run_id,
        artifact_type=_SEMANTIC_REPORT_ARTIFACT,
        node_name="semantic_duplicate_adjudication_node",
        storage_subpath=_SEMANTIC_REPORT_SUBPATH,
        payload=payload,
    )
    await db.commit()


def _empty_result(package: Dict[str, Any], warning: str) -> Dict[str, Any]:
    return SemanticCanonicalizationResult(
        canonical_state_set_id="",
        source_ui_state_package_id=package.get("ui_state_package_id"),
        canonical_states=[],
        non_merged_state_ids=[],
        excluded_state_ids=[],
        merge_decisions=[],
        canonicalization_warnings=[warning] if warning else [],
    ).model_dump()


async def run_semantic_canonicalization(
    db: AsyncSession,
    run_id: str,
    ui_state_package: Dict[str, Any],
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("semantic_canonicalization_started", run_id=run_id)

    extracted_states: List[Any] = (
        ui_state_package.get("extracted_states") or ui_state_package.get("state_catalog") or []
    )
    if not extracted_states:
        r = _empty_result(ui_state_package, "NO_STATES")
        await _persist_semantic_report(db, run_id, r)
        return r

    system_instruction = prompt_manager.get_prompt("semantic_duplicate")

    payload = {
        "schema_version": ui_state_package.get("schema_version", "1.0"),
        "agent_name": "ui_state_extraction_agent",
        "ui_state_package_id": ui_state_package.get("ui_state_package_id", "unknown"),
        "extracted_states": extracted_states,
    }
    user_instruction = (
        "Analyze the following UIStatePackage and produce semantic canonicalization JSON.\n"
        f"{json.dumps(payload, indent=2)}"
    )

    response = await model_adapter.call_text_structured(
        task_name="semantic_canonicalization",
        run_id=run_id,
        node_name="semantic_duplicate_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=SemanticCanonicalizationResult,
        prompt_name="semantic_duplicate_prompt",
        prompt_version="v1",
        provider_override=settings.SEMANTIC_DUPLICATE_MODEL_PROVIDER,
        model_name_override=settings.SEMANTIC_DUPLICATE_MODEL_NAME,
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Semantic Canonicalization failed: {response.error}")
        r = _empty_result(ui_state_package, str(response.error or "LLM_FAILED"))
        r["report"] = {"error": str(response.error)}
        await _persist_semantic_report(db, run_id, r)
        return r

    result: SemanticCanonicalizationResult = response.parsed_output

    for cstate in result.canonical_states:
        await db.execute(
            update(UIState)
            .where(UIState.id == cstate.representative_state_id, UIState.run_id == run_id)
            .values(is_canonical=True, canonical_id=cstate.canonical_state_id)
        )
        if cstate.member_state_ids:
            await db.execute(
                update(UIState)
                .where(UIState.id.in_(cstate.member_state_ids), UIState.run_id == run_id)
                .values(is_canonical=False, canonical_id=cstate.canonical_state_id)
            )

    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("semantic_canonicalization_completed", run_id=run_id, duration_ms=duration_ms)

    out = result.model_dump()
    out["report"] = {"canonical_state_count": len(result.canonical_states)}
    await _persist_semantic_report(db, run_id, out)
    return out
