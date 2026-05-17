"""
Screen Intent Service — Extracts local user goals (ScreenBehaviourIntents) from interaction groups.
LLM emits ID-only drafts; backend validates, hydrates, and persists catalogue rows.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.screen_intent import ScreenBehaviourIntent
from app.model_providers import model_adapter
from app.model_providers.schemas import ScreenBehaviourIntentA2, ScreenIntentExtractionV2Result, UnresolvedScreenGroupA2
from app.services.screen_intent_prompt_render import render_phase2_taxonomy_system_suffix
from app.services.screen_intent_validation import build_allowed_constraints, process_screen_intents_for_state


def _generate_screen_intent_id() -> str:
    return f"sbi_{uuid.uuid4().hex[:12]}"


def _rich_user_instruction_bundle(state_id: str, screen_purpose: Any, enriched_groups: Any, allowed: Dict[str, Any]) -> str:
    payload = {
        "state_id": state_id,
        "screen_purpose": screen_purpose,
        "enriched_groups": enriched_groups,
        **allowed,
    }
    return (
        "Extract Screen Behaviour Intents for this UI state.\n"
        "The JSON payload MUST be honoured for ID grounding — use ONLY ids listed in "
        "the allowed_* maps.\n"
        f"{json.dumps(payload, indent=2)}\n"
    )


async def run_screen_intent_extraction(
    db: AsyncSession, run_id: str, state_catalog: List[Dict[str, Any]]
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("screen_intent_extraction_started", run_id=run_id, node_name="screen_intent_extraction")

    if not state_catalog:
        log_event("screen_intent_extraction_skipped", run_id=run_id, reason="NO_STATES")
        return {
            "screen_intent_package_id": f"sbi_pkg_{uuid.uuid4().hex[:12]}",
            "screen_intent_catalog": [],
            "report": {},
        }

    base_prompt = prompt_manager.get_prompt("prompt_screen_behaviour_intent_extraction_v2").strip()
    system_instruction = f"{base_prompt}\n\n{render_phase2_taxonomy_system_suffix()}"
    semaphore = asyncio.Semaphore(settings.SCREEN_INTENT_MAX_CONCURRENCY)

    async def _extract_intent_for_state(state: Dict[str, Any]) -> Any:
        async with semaphore:
            groups = state.get("interaction_groups") or []

            lookup: Dict[str, Dict[str, Any]] = {}
            for el in state.get("visible_elements", []) or []:
                lookup[el["element_id"]] = el
            for ac in state.get("available_actions", []) or []:
                lookup[ac["action_id"]] = ac
            for fb in state.get("visible_feedback", []) or []:
                lookup[fb["feedback_id"]] = fb

            enriched_groups = []
            for g in groups:
                eg = dict(g)
                eg["elements_metadata"] = [lookup.get(eid) for eid in g.get("element_ids", []) if eid in lookup]
                eg["actions_metadata"] = [lookup.get(aid) for aid in g.get("action_ids", []) if aid in lookup]
                eg["feedback_metadata"] = [lookup.get(fid) for fid in g.get("feedback_ids", []) if fid in lookup]
                enriched_groups.append(eg)

            allowed = build_allowed_constraints(state)

            if not groups:
                return {
                    "kind": "no_groups",
                    "state_id": state["state_id"],
                    "llm_payload": ScreenIntentExtractionV2Result(
                        screen_behaviour_intents=[],
                        unresolved_screen_groups=[
                            UnresolvedScreenGroupA2(
                                group_id="__state__",
                                reason_code="no_interaction_group",
                                details=f"No interaction groups for state {state['state_id']}",
                            )
                        ],
                    ),
                }

            user_instruction = _rich_user_instruction_bundle(
                state["state_id"],
                state.get("screen_purpose"),
                enriched_groups,
                allowed,
            )

            return await model_adapter.call_text_structured(
                task_name="screen_intent_extraction",
                run_id=run_id,
                node_name="screen_intent_extraction_node",
                system_instruction=system_instruction,
                user_instruction=user_instruction,
                output_schema=ScreenIntentExtractionV2Result,
                prompt_name="prompt_screen_behaviour_intent_extraction_v2",
                prompt_version="v2_reference_ids",
                provider_override=settings.SCREEN_INTENT_MODEL_PROVIDER,
                model_name_override=settings.SCREEN_INTENT_MODEL_NAME,
            )

    outcomes = await asyncio.gather(
        *(_extract_intent_for_state(state) for state in state_catalog),
        return_exceptions=True,
    )

    screen_intent_catalog: List[Dict[str, Any]] = []
    merged_unresolved: List[Dict[str, Any]] = []
    skipped_states: List[Dict[str, Any]] = []
    per_state_summaries: List[Dict[str, Any]] = []
    failed_states = 0
    warnings: List[str] = []

    for state, outcome in zip(state_catalog, outcomes):
        sid = state["state_id"]

        if isinstance(outcome, Exception):
            logger.error(
                "Screen Intent Extraction exception for state %s: %s",
                sid,
                outcome,
                exc_info=(type(outcome), outcome, outcome.__traceback__),
            )
            failed_states += 1
            warnings.append(f"Failed for state {sid}: {str(outcome)}")
            continue

        llm_payload: ScreenIntentExtractionV2Result
        draft_raw_outer: Dict[str, Any] | None = None

        if isinstance(outcome, dict) and outcome.get("kind") == "no_groups":
            skipped_states.append({"state_id": sid, "reason_code": "no_interaction_group"})
            llm_payload = outcome["llm_payload"]
            draft_raw_outer = llm_payload.model_dump(mode="python")
        else:
            response = outcome
            if getattr(response.status, "value", None) != "success" or not response.parsed_output:
                err_msg = getattr(response, "error", None) or "unknown error"
                logger.error("Screen Intent Extraction provider failure for state %s: %s", sid, err_msg)
                failed_states += 1
                warnings.append(f"Failed for state {sid}: {err_msg}")
                continue
            llm_payload = response.parsed_output
            draft_raw_outer = llm_payload.model_dump(mode="python")

        cat, unst, summary, _ = process_screen_intents_for_state(state, llm_payload, _generate_screen_intent_id)
        per_state_summaries.append(summary)
        merged_unresolved.extend(unst)

        for intent_dict in cat:
            vdetail = intent_dict.pop("_validation_detail", None)
            hydrated = ScreenBehaviourIntentA2.model_validate(intent_dict)
            vid = hydrated.screen_intent_id
            screen_intent_catalog.append(intent_dict)

            draft_snap = None
            if isinstance(vdetail, dict):
                draft_snap = vdetail.get("draft_snapshot")

            db_row = ScreenBehaviourIntent(
                id=vid,
                run_id=run_id,
                state_id=sid,
                source_group_id=hydrated.source_group_id,
                intent_name=hydrated.intent_name,
                intent_kind=hydrated.intent_kind,
                local_user_goal=hydrated.local_user_goal,
                primary_action_json=(
                    hydrated.primary_action.model_dump() if hydrated.primary_action is not None else None
                ),
                selection_options_json=[o.model_dump() for o in hydrated.selection_options],
                commit_action_json=(
                    hydrated.commit_action.model_dump() if hydrated.commit_action is not None else None
                ),
                secondary_actions_json=[a.model_dump() for a in hydrated.secondary_actions],
                local_action_sequence_templates_json=[
                    s.model_dump() for s in hydrated.local_action_sequence_templates
                ],
                required_input_element_ids_json=list(hydrated.required_input_element_ids),
                evidence_json=[e.model_dump() for e in hydrated.evidence_refs],
                confidence=hydrated.confidence,
                model_confidence=hydrated.model_confidence,
                validation_confidence=hydrated.validation_confidence,
                validation_report_json=vdetail,
                raw_model_output_json=draft_snap,
                raw_result_json={
                    "state_id": sid,
                    "full_draft_snapshot": draft_raw_outer,
                    "intent_draft": draft_snap,
                    "validated_intent_catalog_row": hydrated.model_dump(),
                },
            )
            db.add(db_row)

    await db.commit()

    pkg_id = f"sbi_pkg_{uuid.uuid4().hex[:12]}"

    total_val = sum(s.get("validated_intents", 0) for s in per_state_summaries)
    agg_unres: Dict[str, int] = {}
    for s in per_state_summaries:
        for k, v in (s.get("unresolved_reason_counts") or {}).items():
            agg_unres[k] = agg_unres.get(k, 0) + v

    intent_validation_summary = {
        "per_state": per_state_summaries,
        "aggregate_validated_intents": total_val,
        "aggregate_unresolved_reason_codes": agg_unres,
        "skipped_state_count": len(skipped_states),
    }

    report = {
        "run_id": run_id,
        "screen_intent_package_id": pkg_id,
        "total_states_processed": len(state_catalog),
        "total_intents_extracted": total_val,
        "failed_states": failed_states,
        "warnings": warnings,
        "skipped_states": skipped_states,
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("screen_intent_extraction_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "schema_version": "2.1",
        "agent_name": "screen_intent_extraction_agent",
        "screen_intent_package_id": pkg_id,
        "screen_intent_catalog": screen_intent_catalog,
        "unresolved_screen_groups": merged_unresolved,
        "skipped_states": skipped_states,
        "intent_validation_summary": intent_validation_summary,
        "report": report,
    }
