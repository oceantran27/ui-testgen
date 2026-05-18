"""
Transition hydration and trigger action helpers for UI Flow composition.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

_ACTION_ROLE_TO_TRIGGER_TYPE: Dict[str, str] = {
    "select_option": "select_option",
    "input": "input",
    "commit": "invoke_action",
    "confirm": "confirm",
    "cancel": "cancel",
    "navigate": "navigate",
}


def derive_trigger_from_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
    seq = edge.get("action_sequence") or []
    if not seq:
        return {"action_type": "invoke_action", "text": []}
    step0 = seq[0]
    role = str(step0.get("action_role") or "commit").lower()
    action_type = _ACTION_ROLE_TO_TRIGGER_TYPE.get(role, role)
    texts = list(step0.get("action_text") or [])
    return {"action_type": action_type, "text": texts}


def hypothesized_action_from_trigger(trigger: Dict[str, Any]) -> Optional[str]:
    texts = trigger.get("text") or []
    joined = " ".join(str(t) for t in texts).strip()
    if joined:
        return joined
    at = (trigger.get("action_type") or "").strip()
    return at or None


def normalize_ordering_strength(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("strong", "medium"):
        return s
    return "medium"


def hydrate_flow_edges_for_compose(
    flow: Dict[str, Any],
    candidate_edge_map: Dict[str, Dict[str, Any]],
    transition_id_by_candidate_edge_id: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Build internal transition / alternative_outcome dicts consumed by flow composition.
    """
    tid_map = transition_id_by_candidate_edge_id or {}
    transitions: List[Dict[str, Any]] = []
    for eid in flow.get("transition_edge_ids") or []:
        edge = candidate_edge_map.get(eid)
        if not edge:
            continue
        trig = derive_trigger_from_edge(edge)
        seq = edge.get("action_sequence") or []
        sg = seq[0].get("source_group_id") if seq else None
        si = seq[0].get("source_screen_intent_id") if seq else None
        transitions.append(
            {
                "from_state": edge["from_state"],
                "to_state": edge["to_state"],
                "relation_type": "direct_transition",
                "trigger_action": trig,
                "source_group_id": sg,
                "source_screen_intent_id": si,
                "candidate_edge_id": eid,
                "transition_id": tid_map.get(eid),
                "action_sequence": seq,
                "edge_kind": edge.get("edge_kind"),
            }
        )

    alternative_outcomes: List[Dict[str, Any]] = []
    for eid in flow.get("alternative_outcome_edge_ids") or []:
        edge = candidate_edge_map.get(eid)
        if not edge:
            continue
        trig = derive_trigger_from_edge(edge)
        seq = edge.get("action_sequence") or []
        sg = seq[0].get("source_group_id") if seq else None
        si = seq[0].get("source_screen_intent_id") if seq else None
        alternative_outcomes.append(
            {
                "source_state": edge["from_state"],
                "outcome_states": [edge["to_state"]],
                "trigger_action": trig,
                "relation_type": "alternative_outcome",
                "source_group_id": sg,
                "source_screen_intent_id": si,
                "candidate_edge_id": eid,
                "transition_id": tid_map.get(eid),
                "action_sequence": seq,
                "edge_kind": edge.get("edge_kind"),
            }
        )

    return transitions, alternative_outcomes
