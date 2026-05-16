"""
Flow Context Builder Service — Combines UI states, interaction groups, and screen intents into FlowStateCards.
"""
import time
import uuid
from typing import Any, Dict, List

from app.core.logging import log_event


async def run_flow_context_builder(
    run_id: str,
    state_catalog: List[Dict[str, Any]],
    screen_intent_catalog: List[Dict[str, Any]]
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("flow_context_builder_started", run_id=run_id, node_name="flow_context_builder")

    flow_state_cards: List[Dict[str, Any]] = []

    # Map state_id to its intents
    intents_by_state: Dict[str, List[Dict[str, Any]]] = {}
    for intent in screen_intent_catalog:
        state_id = intent.get("source_state_id")
        if state_id:
            intents_by_state.setdefault(state_id, []).append(intent)

    for state in state_catalog:
        state_id = state.get("state_id")
        
        # Build Flow State Card
        card = {
            "state_id": state_id,
            "screen_type": state.get("screen_type"),
            "screen_purpose": state.get("screen_purpose"),
            "domain": state.get("domain"),
            "interaction_groups": state.get("interaction_groups", []),
            "screen_behaviour_intents": intents_by_state.get(state_id, [])
        }
        flow_state_cards.append(card)

    pkg_id = f"fc_pkg_{uuid.uuid4().hex[:12]}"
    
    report = {
        "run_id": run_id,
        "flow_context_package_id": pkg_id,
        "total_cards_built": len(flow_state_cards),
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("flow_context_builder_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "schema_version": "1.0",
        "agent_name": "flow_context_builder_agent",
        "flow_context_package_id": pkg_id,
        "flow_state_cards": flow_state_cards,
        "report": report,
    }
