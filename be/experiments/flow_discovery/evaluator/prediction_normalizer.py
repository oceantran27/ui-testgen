"""Map raw ``GlobalFlowDiscoveryResult``-shaped JSON to evaluation-facing normalized predictions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from experiments.flow_discovery.gt_converter import transition_converter
from experiments.flow_discovery.gt_converter.transition_converter import build_transitions
from experiments.flow_discovery.schemas.ground_truth_schema import (
    GroundTruthFlowPackage,
    GroundTruthTransition,
)


def _synthetic_catalog_card(state_pkg_catalog_id: str, gt_pkg: GroundTruthFlowPackage) -> Dict[str, Any]:
    st = next((s for s in gt_pkg.states if s.catalog_state_id == state_pkg_catalog_id), None)
    if st is None:
        return {
            "state_id": state_pkg_catalog_id,
            "taxonomy": {},
            "visible_elements": [],
            "available_actions": [],
            "visible_feedback": [],
        }
    ve = st.visible_evidence
    elements: List[dict] = []
    for h in ve.headings:
        elements.append({"element_type": "heading", "text": [h]})
    for t in ve.texts:
        elements.append({"element_type": "text", "text": [t]})
    actions: List[dict] = []
    for a in gt_pkg.actions:
        if a.source_state_gt_id != st.gt_state_id:
            continue
        tid = str(a.system_action_id or "").strip()
        actions.append(
            {
                "action_id": tid,
                "action_type": str(a.action_type or ""),
                "text": [a.action_text] if a.action_text else [],
            },
        )
    feedback = [{"text": [fb]} for fb in ve.feedback]
    return {
        "state_id": st.catalog_state_id,
        "taxonomy": {
            "screen_type": st.screen_type,
            "outcome_state_type": st.outcome_state_type,
            **(st.taxonomy or {}),
        },
        "visible_elements": elements,
        "available_actions": actions,
        "visible_feedback": feedback,
    }


def build_card_index_for_eval(
    gt_pkg: GroundTruthFlowPackage,
    compressed_catalog_package: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    if compressed_catalog_package:
        cards = compressed_catalog_package.get("compressed_catalog") or []
        if isinstance(cards, list):
            from experiments.flow_discovery.gt_converter.state_converter import build_catalog_state_index

            return build_catalog_state_index([c for c in cards if isinstance(c, dict)])
    return {s.catalog_state_id: _synthetic_catalog_card(s.catalog_state_id, gt_pkg) for s in gt_pkg.states}


def catalog_to_gt_map(gt_pkg: GroundTruthFlowPackage) -> Dict[str, str]:
    return {s.catalog_state_id: s.gt_state_id for s in gt_pkg.states}


def normalized_prediction_from_model(
    model_dict: Dict[str, Any],
    gt_pkg: GroundTruthFlowPackage,
    *,
    compressed_catalog_package: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build normalized prediction dict (transitions, flows, branch-like groups)."""

    catalog_to_gt = catalog_to_gt_map(gt_pkg)
    card_by_catalog = build_card_index_for_eval(gt_pkg, compressed_catalog_package)

    built: List[GroundTruthTransition] = build_transitions(
        gt_pkg.app_id,
        model_dict,
        catalog_to_gt,
        card_by_catalog,
    )

    predicted_transitions: List[Dict[str, Any]] = []
    for i, tx in enumerate(built, start=1):
        src = "alternative_outcomes"
        if tx.proposal_source == transition_converter.PROPOSAL_SPINE:
            src = "ordered_steps"
        predicted_transitions.append(
            {
                "pred_transition_id": f"pred_t_{i:03d}",
                "from_state_id": tx.from_state_id,
                "to_state_id": tx.to_state_id,
                "trigger_action_text": tx.trigger_action_text,
                "trigger_action_id": tx.trigger_action_id,
                "outcome_type": tx.outcome_type,
                "source": src,
                "proposal_flow_id": tx.proposal_flow_id,
            },
        )

    predicted_flows: List[Dict[str, Any]] = []
    fctr = 0
    for flow in model_dict.get("candidate_flows") or []:
        if not isinstance(flow, dict):
            continue
        fid = str(flow.get("flow_id") or "").strip() or "unknown"
        fctr += 1
        oid: List[str] = []
        for st in flow.get("ordered_steps") or []:
            if isinstance(st, dict):
                cid = str(st.get("state_id") or "").strip()
                if cid in catalog_to_gt:
                    oid.append(catalog_to_gt[cid])
        predicted_flows.append(
            {
                "pred_flow_id": f"pred_f_{fctr:03d}",
                "source_flow_id": fid,
                "ordered_state_ids": oid,
            },
        )

    branch_groups: List[Dict[str, Any]] = []
    pseudo_tx: List[GroundTruthTransition] = []
    for row in predicted_transitions:
        pseudo_tx.append(
            GroundTruthTransition(
                gt_transition_id=row["pred_transition_id"],
                from_state_id=row["from_state_id"],
                to_state_id=row["to_state_id"],
                trigger_action_text=row["trigger_action_text"],
                outcome_type=row["outcome_type"],
                proposal_source="pred",
            ),
        )
    grouped = transition_converter.transitions_by_branch_key(pseudo_tx)
    bg_ctr = 0
    for key, pids in grouped.items():
        if len(pids) < 2:
            continue
        parts = key.split("||", 1)
        anchor = parts[0] if parts else ""
        trig = parts[1] if len(parts) > 1 else ""
        bg_ctr += 1
        branch_groups.append(
            {
                "pred_branch_id": f"pred_bg_{bg_ctr:03d}",
                "anchor_source_gt_state_id": anchor,
                "normalized_trigger": trig,
                "pred_transition_ids": list(dict.fromkeys(pids)),
            },
        )

    return {
        "predicted_transitions": predicted_transitions,
        "predicted_flows": predicted_flows,
        "predicted_branch_groups": branch_groups,
    }
