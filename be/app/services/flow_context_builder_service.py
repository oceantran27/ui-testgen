"""
Flow Context Builder Service — Combines UI states, interaction groups, and screen intents into FlowStateCards.
"""
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List

from app.core.logging import log_event
from app.constants.ui_screen_taxonomy import normalize_screen_type, screen_type_supports_empty_state_heuristic


def _unpack_screen_intent_input(screen_intents: Any) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Support legacy callers passing only the catalogue list."""
    if isinstance(screen_intents, list):
        return screen_intents, {}
    pkg = dict(screen_intents or {})
    return pkg.get("screen_intent_catalog", []) or [], pkg


async def run_flow_context_builder(
    run_id: str,
    state_catalog: List[Dict[str, Any]],
    screen_intents: Any,
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("flow_context_builder_started", run_id=run_id, node_name="flow_context_builder")

    screen_intent_catalog, screen_intent_pkg = _unpack_screen_intent_input(screen_intents)
    package_unresolved: List[Dict[str, Any]] = list(screen_intent_pkg.get("unresolved_screen_groups") or [])
    summary_pkg: Dict[str, Any] = dict(screen_intent_pkg.get("intent_validation_summary") or {})
    skipped_states: List[Dict[str, Any]] = list(screen_intent_pkg.get("skipped_states") or [])

    flow_state_cards: List[Dict[str, Any]] = []

    intents_by_state: Dict[str, List[Dict[str, Any]]] = {}
    for intent in screen_intent_catalog:
        sid = intent.get("source_state_id")
        if sid:
            intents_by_state.setdefault(sid, []).append(intent)

    unresolved_by_state: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in package_unresolved:
        sid_key = row.get("source_state_id")
        if sid_key:
            unresolved_by_state[sid_key].append(row)

    per_state_summary_lookup: Dict[str, Dict[str, Any]] = {}
    for blk in summary_pkg.get("per_state") or []:
        s = blk.get("state_id")
        if s:
            per_state_summary_lookup[s] = blk

    for state in state_catalog:
        state_id = state.get("state_id")

        visible_text = []
        for e in state.get("visible_elements", []):
            visible_text.extend(e.get("text", []))

        action_texts = []
        for a in state.get("available_actions", []):
            action_texts.extend(a.get("text", []))

        feedback_texts = []
        for f in state.get("visible_feedback", []):
            feedback_texts.extend(f.get("text", []))

        outcome_state_type = state.get("outcome_state_type", "neutral")
        if outcome_state_type == "normal":
            outcome_state_type = "neutral"
        screen_type = normalize_screen_type(state.get("screen_type"))
        presentation_scope = state.get("presentation_scope") or "unknown"
        if screen_type_supports_empty_state_heuristic(screen_type):
            text_corpus = [t.lower() for t in visible_text]
            empty_keywords = [
                "no upcoming",
                "no items",
                "empty",
                "no active",
                "no bookings",
                "no orders",
                "no reservations",
                "no results",
            ]
            has_empty_clue = any(any(kw in t for kw in empty_keywords) for t in text_corpus)
            if has_empty_clue:
                outcome_state_type = "empty"

        intents_for_state = intents_by_state.get(state_id, [])
        card_summary = dict(per_state_summary_lookup.get(state_id, {}))

        card = {
            "state_id": state_id,
            "upload_order": state.get("upload_order"),
            "screen_type": screen_type,
            "presentation_scope": presentation_scope,
            "screen_purpose": state.get("screen_purpose"),
            "outcome_state_type": outcome_state_type,
            "domain": state.get("domain"),
            "visible_text": visible_text,
            "action_texts": action_texts,
            "feedback_texts": feedback_texts,
            "interaction_groups": state.get("interaction_groups", []),
            "screen_behaviour_intents": intents_for_state,
            "validated_screen_behaviour_intents": intents_for_state,
            "unresolved_screen_groups": unresolved_by_state.get(state_id, []),
            "intent_validation_summary": card_summary if card_summary else {
                "state_id": state_id,
                "note": "no per-state Phase 2 summary attached (legacy package)",
            },
        }
        flow_state_cards.append(card)

    pkg_id = f"fc_pkg_{uuid.uuid4().hex[:12]}"

    report = {
        "run_id": run_id,
        "flow_context_package_id": pkg_id,
        "total_cards_built": len(flow_state_cards),
        "skipped_states_from_phase2": skipped_states,
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("flow_context_builder_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "schema_version": "1.1",
        "agent_name": "flow_context_builder_agent",
        "flow_context_package_id": pkg_id,
        "flow_state_cards": flow_state_cards,
        "package_unresolved_screen_groups": package_unresolved,
        "package_intent_validation_summary": summary_pkg,
        "report": report,
    }
