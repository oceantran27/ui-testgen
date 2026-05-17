"""
Post-LLM validation and deterministic repair for intent-aware flow discovery (edge-ID contract).
"""
from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from app.constants.edge_taxonomy import NEGATIVE_OUTCOME_TYPES
from app.model_providers.schemas import (
    EdgeDecisionA4,
    FlowDiscoveryA3,
    SemanticClusterA3,
    UIFlowDiscoveryResult,
    UncertainRelationA3,
)
from app.services.intent_aware_flow_discovery_hydrate import rebuild_ordered_states_from_edges

POST_TERMINAL_OUTCOMES: Set[str] = {"success", "confirmation_required"}

FIELD_PRIORITY: Tuple[str, ...] = (
    "transition_edge_ids",
    "alternative_outcome_edge_ids",
    "local_interaction_edge_ids",
    "uncertain_edge_ids",
)


def _priority_rank(field: str) -> int:
    try:
        return FIELD_PRIORITY.index(field)
    except ValueError:
        return 99


def _negative_edge_kind(edge: Dict[str, Any]) -> bool:
    ek = str(edge.get("edge_kind") or "")
    return ek in NEGATIVE_OUTCOME_TYPES


def _coherent_transition_chain(
    transition_edge_ids: List[str],
    candidate_edge_map: Dict[str, Dict[str, Any]],
    warnings: List[str],
    flow_id: str,
) -> List[str]:
    ok: List[str] = []
    for eid in transition_edge_ids:
        edge = candidate_edge_map.get(eid)
        if not edge:
            continue
        if not ok:
            ok.append(eid)
            continue
        prev_to = candidate_edge_map[ok[-1]]["to_state"]
        cur_from = edge["from_state"]
        if prev_to == cur_from:
            ok.append(eid)
        else:
            warnings.append(
                f"VALIDATION_TRANSITION_CHAIN_BROKEN:{flow_id}:{eid}:{prev_to}!={cur_from}"
            )
            break
    return ok


def _resolve_global_bucket_conflicts(flows: List[Dict[str, Any]], warnings: List[str]) -> None:
    """Each edge id appears in at most one bucket field across all flows (highest-priority bucket wins)."""
    placements: Dict[str, List[Tuple[int, str]]] = {}
    for fi, flow in enumerate(flows):
        for field in FIELD_PRIORITY:
            for eid in flow.get(field) or []:
                placements.setdefault(eid, []).append((fi, field))

    winners: Dict[str, Tuple[int, str]] = {}
    for eid, places in placements.items():
        best = min(places, key=lambda p: _priority_rank(p[1]))
        winners[eid] = best
        for fi, field in places:
            if (fi, field) != best:
                warnings.append(
                    f"VALIDATION_GLOBAL_BUCKET_CONFLICT:{eid}:keep:{best[1]}:flow:{best[0]}:drop:{field}:flow:{fi}"
                )

    for fi, flow in enumerate(flows):
        for field in FIELD_PRIORITY:
            flow[field] = [
                eid
                for eid in (flow.get(field) or [])
                if winners.get(eid) == (fi, field)
            ]


def validate_and_repair_flow_discovery(
    result: UIFlowDiscoveryResult,
    candidate_edge_map: Dict[str, Dict[str, Any]],
    state_card_by_id: Dict[str, Dict[str, Any]],
) -> Tuple[UIFlowDiscoveryResult, Dict[str, Any]]:
    warnings: List[str] = []
    meta: Dict[str, Any] = {"validation_failed": False, "flows_low_confidence": []}

    raw_flows = [f.model_dump() for f in result.candidate_flows]
    known_ids = set(candidate_edge_map.keys())

    # --- sanitize unknown edge IDs ---
    for fi, flow in enumerate(raw_flows):
        fid = flow.get("flow_id") or str(fi)
        for key in FIELD_PRIORITY:
            raw = list(flow.get(key) or [])
            cleaned = []
            for eid in raw:
                if eid in known_ids:
                    cleaned.append(eid)
                else:
                    warnings.append(f"VALIDATION_UNKNOWN_EDGE_ID:{fid}:{eid}")
            flow[key] = cleaned

    uncertain_global: Set[str] = set()
    for flow in raw_flows:
        uncertain_global.update(flow.get("uncertain_edge_ids") or [])
    for d in result.edge_decisions:
        if d.decision == "uncertain":
            uncertain_global.add(d.candidate_edge_id)

    # Uncertain edges must never appear on main transition lists (overrides bucket priority).
    for fi, flow in enumerate(raw_flows):
        fid = flow.get("flow_id") or str(fi)
        te = list(flow.get("transition_edge_ids") or [])
        stripped = [e for e in te if e not in uncertain_global]
        if len(stripped) != len(te):
            warnings.append(f"VALIDATION_UNCERTAIN_STRIPPED_FROM_TRANSITION:{fid}")
            flow["transition_edge_ids"] = stripped

    _resolve_global_bucket_conflicts(raw_flows, warnings)

    # --- per-flow structural repairs ---
    for fi, flow in enumerate(raw_flows):
        fid = flow.get("flow_id") or str(fi)
        te = list(flow.get("transition_edge_ids") or [])
        alt = list(flow.get("alternative_outcome_edge_ids") or [])
        loc = list(flow.get("local_interaction_edge_ids") or [])
        unc = list(flow.get("uncertain_edge_ids") or [])

        te_set = set(te)
        alt = [e for e in alt if e not in te_set]
        loc = [e for e in loc if e not in te_set]
        unc = [e for e in unc if e not in te_set]

        fixed_te: List[str] = []
        promoted_alt: List[str] = []
        for eid in te:
            edge = candidate_edge_map.get(eid)
            if not edge:
                continue
            if _negative_edge_kind(edge):
                warnings.append(f"VALIDATION_NEGATIVE_EDGE_MOVED_TO_ALT:{fid}:{eid}")
                promoted_alt.append(eid)
                continue
            fixed_te.append(eid)

        te = fixed_te
        te_set = set(te)
        alt = list(dict.fromkeys([e for e in promoted_alt + alt if e not in te_set]))

        flow["transition_edge_ids"] = te
        flow["alternative_outcome_edge_ids"] = alt
        flow["local_interaction_edge_ids"] = loc
        flow["uncertain_edge_ids"] = unc

        te = _coherent_transition_chain(te, candidate_edge_map, warnings, fid)
        flow["transition_edge_ids"] = te

        rebuilt_states = rebuild_ordered_states_from_edges(te, candidate_edge_map)
        llm_states = list(flow.get("ordered_states") or [])
        flow["ordered_states"] = rebuilt_states if te else llm_states

        invalid_states = [s for s in flow["ordered_states"] if s not in state_card_by_id]
        if invalid_states:
            warnings.append(f"VALIDATION_UNKNOWN_STATE_IDS:{fid}:{invalid_states}")
            flow["ordered_states"] = [s for s in flow["ordered_states"] if s in state_card_by_id]

        if te and rebuilt_states != llm_states:
            warnings.append(f"VALIDATION_ORDERED_STATES_REALIGNED:{fid}")

        ordered_states = list(flow["ordered_states"])
        te = list(flow["transition_edge_ids"])
        if len(ordered_states) >= 2 and te:
            trunc_idx = None
            for i in range(len(te)):
                land_idx = i + 1
                if land_idx >= len(ordered_states):
                    break
                landing = ordered_states[land_idx]
                oc = str(state_card_by_id.get(landing, {}).get("outcome_state_type") or "neutral")
                if oc in POST_TERMINAL_OUTCOMES:
                    trunc_idx = i
                    break
            if trunc_idx is not None and trunc_idx < len(te) - 1:
                flow["transition_edge_ids"] = te[: trunc_idx + 1]
                flow["ordered_states"] = rebuild_ordered_states_from_edges(
                    flow["transition_edge_ids"], candidate_edge_map
                )
                warnings.append(f"VALIDATION_POST_TERMINAL_TRUNCATED:{fid}")

        alt_overlap = set(flow["transition_edge_ids"]) & set(flow["alternative_outcome_edge_ids"])
        if alt_overlap:
            flow["alternative_outcome_edge_ids"] = [
                e for e in flow["alternative_outcome_edge_ids"] if e not in flow["transition_edge_ids"]
            ]
            warnings.append(f"VALIDATION_ALT_OVERLAP_TRANSITION_STRIPPED:{fid}")

        raw_flows[fi] = flow

    # --- semantic clusters ---
    repaired_clusters: List[SemanticClusterA3] = []
    for cl in result.semantic_clusters:
        d = cl.model_dump()
        states = [s for s in (d.get("states") or []) if s in state_card_by_id]
        dropped = set(d.get("states") or []) - set(states)
        if dropped:
            warnings.append(f"VALIDATION_CLUSTER_UNKNOWN_STATES:{d.get('cluster_id')}:{sorted(dropped)}")
        d["states"] = states
        repaired_clusters.append(SemanticClusterA3(**d))

    # --- uncertain_relations ---
    repaired_uncertain: List[UncertainRelationA3] = []
    for ur in result.uncertain_relations:
        d = ur.model_dump()
        eid = d.get("candidate_edge_id")
        if eid not in known_ids:
            warnings.append(f"VALIDATION_UNCERTAIN_REL_UNKNOWN_EDGE:{eid}")
            continue
        repaired_uncertain.append(UncertainRelationA3(**d))

    # --- edge_decisions ---
    repaired_decisions: List[EdgeDecisionA4] = []
    for d in result.edge_decisions:
        if d.candidate_edge_id not in known_ids:
            warnings.append(f"VALIDATION_EDGE_DECISION_UNKNOWN_ID:{d.candidate_edge_id}")
            continue
        repaired_decisions.append(d)

    repaired_flow_models = [FlowDiscoveryA3(**f) for f in raw_flows]

    before_flow_ct = len(result.candidate_flows)
    after_flow_ct = len(
        [
            f
            for f in repaired_flow_models
            if f.transition_edge_ids or f.alternative_outcome_edge_ids
        ]
    )
    if before_flow_ct > 0 and after_flow_ct == 0:
        meta["validation_failed"] = True
        warnings.append("VALIDATION_EMPTY_AFTER_REPAIR")

    merged_warnings = list(result.discovery_warnings) + warnings

    repaired = UIFlowDiscoveryResult(
        flow_discovery_result_id=result.flow_discovery_result_id,
        source_canonical_state_set_id=result.source_canonical_state_set_id,
        edge_decisions=repaired_decisions,
        candidate_flows=repaired_flow_models,
        semantic_clusters=repaired_clusters,
        uncertain_relations=repaired_uncertain,
        discovery_warnings=merged_warnings,
    )

    return repaired, meta
