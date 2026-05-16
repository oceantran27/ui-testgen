"""
Screen Intent Service — Extracts local user goals (ScreenBehaviourIntents) from interaction groups.
"""
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.screen_intent import ScreenBehaviourIntent
from app.model_providers import model_adapter
from app.model_providers.schemas import ScreenIntentExtractionV2Result
from app.services.storage_service import storage_service


def _generate_screen_intent_id() -> str:
    return f"sbi_{uuid.uuid4().hex[:12]}"


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

    system_instruction = prompt_manager.get_prompt("prompt_screen_behaviour_intent_extraction_v2")
    semaphore = asyncio.Semaphore(settings.LLM_FLOW_DISCOVERY_MAX_CONCURRENCY)

    async def _extract_intent_for_state(state: Dict[str, Any]) -> Any:
        async with semaphore:
            groups = state.get("interaction_groups", [])
            if not groups:
                return None
            
            # Enrich groups with full metadata from state catalog
            # We build a lookup map: id -> full_object
            lookup: Dict[str, Dict[str, Any]] = {}
            for el in state.get("visible_elements", []):
                lookup[el["element_id"]] = el
            for ac in state.get("available_actions", []):
                lookup[ac["action_id"]] = ac
            for fb in state.get("visible_feedback", []):
                lookup[fb["feedback_id"]] = fb

            enriched_groups = []
            for g in groups:
                eg = g.copy()
                # Inject full objects instead of just IDs for the LLM to see text/type
                eg["elements_metadata"] = [lookup.get(eid) for eid in g.get("element_ids", []) if eid in lookup]
                eg["actions_metadata"] = [lookup.get(aid) for aid in g.get("action_ids", []) if aid in lookup]
                eg["feedback_metadata"] = [lookup.get(fid) for fid in g.get("feedback_ids", []) if fid in lookup]
                enriched_groups.append(eg)
                
            user_instruction = (
                f"Extract Screen Behaviour Intents for this screen: {state['state_id']}\n"
                f"Purpose: {state.get('screen_purpose')}\n"
                f"Interaction Groups (Enriched): {json.dumps(enriched_groups, indent=2)}\n"
            )

            return await model_adapter.call_text_structured(
                task_name="screen_intent_extraction",
                run_id=run_id,
                node_name="screen_intent_extraction_node",
                system_instruction=system_instruction,
                user_instruction=user_instruction,
                output_schema=ScreenIntentExtractionV2Result,
                prompt_name="prompt_screen_behaviour_intent_extraction_v2",
                prompt_version="v1",
                provider_override=settings.LLM_FLOW_DISCOVERY_MODEL_PROVIDER,
                model_name_override=settings.LLM_FLOW_DISCOVERY_MODEL_NAME,
            )

    outcomes = await asyncio.gather(
        *(_extract_intent_for_state(state) for state in state_catalog),
        return_exceptions=True,
    )

    screen_intent_catalog: List[Dict[str, Any]] = []
    total_intents = 0
    failed_states = 0
    warnings = []

    for state, response in zip(state_catalog, outcomes):
        if response is None:
            continue
            
        if isinstance(response, Exception):
            logger.error(
                "Screen Intent Extraction failed for state %s: %s",
                state["state_id"],
                response,
                exc_info=response,
            )
            failed_states += 1
            warnings.append(f"Failed for state {state['state_id']}: {str(response)}")
            continue

        if response.status.value != "success" or not response.parsed_output:
            logger.error(f"Screen Intent Extraction failed for state {state['state_id']}: {response.error}")
            failed_states += 1
            warnings.append(f"Failed for state {state['state_id']}: {response.error}")
            continue

        result_data: ScreenIntentExtractionV2Result = response.parsed_output
        
        for intent in result_data.screen_behaviour_intents:
            intent.screen_intent_id = _generate_screen_intent_id()
            db_intent = ScreenBehaviourIntent(
                id=intent.screen_intent_id,
                run_id=run_id,
                state_id=state["state_id"],
                source_group_id=intent.source_group_id,
                intent_name=intent.intent_name,
                intent_kind=intent.intent_kind,
                local_user_goal=intent.local_user_goal,
                primary_action_json=(
                    intent.primary_action.model_dump()
                    if intent.primary_action is not None
                    else None
                ),
                selection_options_json=[
                    o.model_dump() for o in intent.selection_options
                ],
                commit_action_json=(
                    intent.commit_action.model_dump()
                    if intent.commit_action is not None
                    else None
                ),
                secondary_actions_json=[
                    a.model_dump() for a in intent.secondary_actions
                ],
                local_action_sequence_templates_json=[
                    s.model_dump() for s in intent.local_action_sequence_templates
                ],
                required_input_groups_json=intent.required_input_groups,
                evidence_json=intent.evidence,
                confidence=intent.confidence,
                raw_result_json=intent.model_dump()
            )
            db.add(db_intent)
            
            # Create dictionary format for catalog
            intent_dict = intent.model_dump()
            intent_dict["source_state_id"] = state["state_id"]
            screen_intent_catalog.append(intent_dict)
            total_intents += 1

    await db.commit()

    pkg_id = f"sbi_pkg_{uuid.uuid4().hex[:12]}"
    
    report = {
        "run_id": run_id,
        "screen_intent_package_id": pkg_id,
        "total_states_processed": len(state_catalog),
        "total_intents_extracted": total_intents,
        "failed_states": failed_states,
        "warnings": warnings,
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("screen_intent_extraction_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "schema_version": "2.0",
        "agent_name": "screen_intent_extraction_agent",
        "screen_intent_package_id": pkg_id,
        "screen_intent_catalog": screen_intent_catalog,
        "report": report,
    }
