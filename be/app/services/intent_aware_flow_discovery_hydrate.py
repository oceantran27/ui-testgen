"""
Hydration helpers for intent-aware flow discovery: derive DB-safe transitions from candidate_edges.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.model_providers.schemas import EdgeDecisionA4


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


def evidence_level_for_edge_id(
    edge_id: str,
    edge_decisions: List[EdgeDecisionA4],
    default: str = "medium",
) -> str:
    for d in edge_decisions:
        if d.candidate_edge_id == edge_id:
            return str(d.evidence_level).strip().lower()
    return default


def reason_code_for_edge_id(edge_id: str, edge_decisions: List[EdgeDecisionA4]) -> Optional[str]:
    for d in edge_decisions:
        if d.candidate_edge_id == edge_id:
            return d.reason_code
    return None


def normalize_ordering_strength(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("strong", "medium"):
        return s
    return "medium"


def compute_flow_confidence(
    transition_edge_ids: List[str],
    alternative_outcome_edge_ids: List[str],
    candidate_edge_map: Dict[str, Dict[str, Any]],
) -> Tuple[float, str]:
    """Weighted heuristic from resolver scores → persisted Flow.confidence + label."""

    def _avg(ids: List[str], weight: float) -> Tuple[float, float]:
        scores = [
            float(candidate_edge_map[e].get("edge_score") or 0.0)
            for e in ids
            if e in candidate_edge_map
        ]
        if not scores:
            return 0.0, 0.0
        return sum(scores) / len(scores), weight * len(scores)

    main_avg, main_w = _avg(transition_edge_ids, 1.0)
    alt_avg, alt_w = _avg(alternative_outcome_edge_ids, 0.35)
    denom = main_w + alt_w
    blended = main_avg if denom == 0 else (main_avg * main_w + alt_avg * alt_w) / denom

    penalty = 0.0
    for eid in transition_edge_ids:
        edge = candidate_edge_map.get(eid) or {}
        flags = edge.get("edge_risk_flags") or []
        penalty += min(12.0, float(len(flags)) * 4.0)

    raw = max(0.0, blended - penalty)

    if raw >= 85.0:
        return 0.9, "high"
    if raw >= 70.0:
        return 0.7, "medium"
    if raw >= 55.0:
        return 0.45, "medium"
    return 0.25, "low"


def build_flow_discovery_decision_report(
    edge_decisions: List[EdgeDecisionA4],
) -> Dict[str, List[str]]:
    accepted: List[str] = []
    rejected: List[str] = []
    local_interactions: List[str] = []
    uncertain_edges: List[str] = []
    for d in edge_decisions:
        eid = d.candidate_edge_id
        if d.decision == "accepted":
            accepted.append(eid)
        elif d.decision == "rejected":
            rejected.append(eid)
        elif d.decision == "local_interaction":
            local_interactions.append(eid)
        elif d.decision == "uncertain":
            uncertain_edges.append(eid)
    return {
        "accepted_edges": accepted,
        "rejected_edges": rejected,
        "local_interactions": local_interactions,
        "uncertain_edges": uncertain_edges,
    }


def hydrate_flow_edges_for_compose(
    flow: Dict[str, Any],
    candidate_edge_map: Dict[str, Dict[str, Any]],
    transition_id_by_candidate_edge_id: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Build legacy-shaped transition / alternative_outcomes lists for _compose_graph_flows.
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


def rebuild_ordered_states_from_edges(
    transition_edge_ids: List[str],
    candidate_edge_map: Dict[str, Dict[str, Any]],
) -> List[str]:
    if not transition_edge_ids:
        return []
    states: List[str] = []
    for i, eid in enumerate(transition_edge_ids):
        edge = candidate_edge_map.get(eid)
        if not edge:
            continue
        if i == 0:
            states.append(edge["from_state"])
        states.append(edge["to_state"])
    return states
