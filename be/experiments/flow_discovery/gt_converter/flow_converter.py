"""Map ``FlowDiscoveryCandidateFlow`` dict rows into ``GroundTruthFlow``."""

from __future__ import annotations

from typing import Dict, List, Sequence

from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlow, GroundTruthTransition


def _terminal_catalog_id(flow: Dict[str, object]) -> str:
    steps = flow.get("ordered_steps") or []
    if isinstance(steps, list) and steps:
        last = steps[-1]
        if isinstance(last, dict):
            return str(last.get("state_id") or "").strip()
    oss = flow.get("ordered_states") or []
    if oss:
        return str(oss[-1]).strip()
    return str(flow.get("entry_state_id") or "").strip()


def classify_semantic_flow_kind(
    flow: Dict[str, object],
    card_by_catalog: Dict[str, Dict[str, object]],
) -> str:
    """Heuristic behavioural label for reviewer (separate from production ``flow_type``)."""

    steps = flow.get("ordered_steps") or []
    if not isinstance(steps, list):
        steps = []

    alternatives = flow.get("alternative_outcomes") or []
    if not steps and alternatives:
        return "navigation_branch"
    if not steps and not alternatives:
        return "empty_result_branch"

    term_c = _terminal_catalog_id(flow)
    card = card_by_catalog.get(term_c, {})
    tax = dict(card.get("taxonomy") or {}) if isinstance(card, dict) else {}
    ost = str(tax.get("outcome_state_type") or "").strip().lower()
    term_outcome = str(flow.get("terminal_outcome") or "").strip().lower()
    cand_type = str(flow.get("flow_type") or "").strip().lower()

    if term_outcome in ("cancel", "cancelled", "dismissed"):
        return "cancellation_branch"
    if cand_type == "branching_flow":
        return "navigation_branch"

    if ost in ("positive", "success", "complete", "done"):
        return "happy_path"
    if ost in ("validation_error", "validation_blocked", "invalid_input"):
        return "validation_branch"
    if ost in ("warning",):
        return "validation_branch"
    if ost in ("error", "negative", "failure", "fatal"):
        return "error_branch"

    scr = str(tax.get("screen_type") or "").lower()
    if "modal" in scr or "overlay" in scr:
        return "modal_branch"

    if cand_type == "single_step_outcome" and isinstance(steps, list) and len(steps) <= 1:
        return "navigation_branch"

    return "navigation_branch"


def build_flows_from_model(
    app_id: str,
    model_dict: Dict[str, object],
    card_by_catalog: Dict[str, Dict[str, object]],
    catalog_to_gt: Dict[str, str],
    transitions: Sequence[GroundTruthTransition],
) -> List[GroundTruthFlow]:
    if not isinstance(model_dict, dict):
        return []

    flows_out: List[GroundTruthFlow] = []
    ctr = 0

    txs = list(transitions)
    cand_flows = model_dict.get("candidate_flows") or []

    for flow in cand_flows:
        if not isinstance(flow, dict):
            continue
        fid = str(flow.get("flow_id") or "").strip() or "unknown"
        ctr += 1
        gfid = f"gt_f_{app_id}_{fid}_{ctr:03d}"

        oid_states: List[str] = []
        for st in flow.get("ordered_steps") or []:
            if isinstance(st, dict):
                cid = str(st.get("state_id") or "").strip()
                if cid in catalog_to_gt:
                    oid_states.append(catalog_to_gt[cid])

        entry_catalog = str(flow.get("entry_state_id") or "").strip()
        entry_gt = catalog_to_gt.get(entry_catalog, oid_states[0] if oid_states else "")

        terminal_c = _terminal_catalog_id(flow)
        term_gt = catalog_to_gt.get(terminal_c, oid_states[-1] if oid_states else "")

        member_tx_ids = [tx.gt_transition_id for tx in txs if tx.proposal_flow_id == fid]

        semantics = classify_semantic_flow_kind(flow, card_by_catalog)

        flows_out.append(
            GroundTruthFlow(
                gt_flow_id=gfid,
                source_flow_id=fid,
                flow_type=str(flow.get("flow_type") or ""),
                semantic_flow_kind=semantics,
                flow_name=str(flow.get("flow_name") or ""),
                ordered_state_ids=oid_states,
                entry_state_id=entry_gt or "",
                terminal_state_id=term_gt or "",
                transition_ids=list(member_tx_ids),
            )
        )

    return flows_out
