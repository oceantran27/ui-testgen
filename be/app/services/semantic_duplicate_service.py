"""
Semantic Canonicalization Service — Agent 2.
Gathers equivalent UI states into canonical representations.
"""
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.ui_state import UIState
from app.model_providers import model_adapter
from app.model_providers.schemas import SemanticCanonicalizationResult, WarningA2
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


def _empty_result(warning: str) -> Dict[str, Any]:
    return SemanticCanonicalizationResult(
        canonical_state_set_id=f"cset_{uuid.uuid4().hex[:12]}",
        unique_states=[],
        deduplication_map=[],
        merge_decisions=[],
        separation_decisions=[],
        warnings=[] if not warning else [WarningA2(type="system", message=warning, affected_states=[])],
    ).model_dump()


async def run_semantic_canonicalization(
    db: AsyncSession,
    run_id: str,
    ui_state_package: Dict[str, Any],
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("semantic_canonicalization_started", run_id=run_id)

    extracted_states: List[Any] = ui_state_package.get("extracted_states") or []
    if not extracted_states:
        r = _empty_result("NO_STATES")
        await _persist_semantic_report(db, run_id, r)
        return r

    system_instruction = prompt_manager.get_prompt("semantic_duplicate")

    user_instruction = (
      "Analyze the following UI states and produce semantic deduplication JSON.\n"
      f"{json.dumps(extracted_states, indent=2)}"
    )

    response = await model_adapter.call_text_structured(
        task_name="semantic_canonicalization",
        run_id=run_id,
        node_name="semantic_duplicate_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=SemanticCanonicalizationResult,
        prompt_name="semantic_duplicate_prompt",
        prompt_version="v2",
        provider_override=settings.SEMANTIC_DUPLICATE_MODEL_PROVIDER,
        model_name_override=settings.SEMANTIC_DUPLICATE_MODEL_NAME,
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Semantic Canonicalization failed: {response.error}")
        r = _empty_result(str(response.error or "LLM_FAILED"))
        r["report"] = {"error": str(response.error)}
        await _persist_semantic_report(db, run_id, r)
        return r

    result: SemanticCanonicalizationResult = response.parsed_output

    for cstate in result.unique_states:
        rep_id = cstate.data.state_id
        # 1. Update representative
        await db.execute(
            update(UIState)
            .where(UIState.id == rep_id, UIState.run_id == run_id)
            .values(is_canonical=True, canonical_id=cstate.canonical_id)
        )
        # 2. Update all members in group
        if cstate.merged_from:
            other_ids = [sid for sid in cstate.merged_from if sid != rep_id]
            if other_ids:
                await db.execute(
                    update(UIState)
                    .where(UIState.id.in_(other_ids), UIState.run_id == run_id)
                    .values(is_canonical=False, canonical_id=cstate.canonical_id)
                )

    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("semantic_canonicalization_completed", run_id=run_id, duration_ms=duration_ms)

    out = result.model_dump()
    out["report"] = {"unique_state_count": len(result.unique_states)}
    await _persist_semantic_report(db, run_id, out)
    return out
