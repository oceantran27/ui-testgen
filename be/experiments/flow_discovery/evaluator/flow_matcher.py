"""Flow-level membership and ordering accuracy."""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from experiments.flow_discovery.evaluator.text_normalize import normalize_trigger_text
from experiments.flow_discovery.schemas.evaluation_schema import FlowEvalItem
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlow, GroundTruthFlowPackage


def _tx_fingerprint(
    from_id: str,
    to_id: str,
    trigger: str,
    outcome: str,
) -> Tuple[str, str, str, str]:
    return (
        from_id,
        to_id,
        normalize_trigger_text(trigger),
        str(outcome or "").strip().lower(),
    )


def _gt_flow_signatures(
    pkg: GroundTruthFlowPackage,
    flow: GroundTruthFlow,
) -> Set[Tuple[str, str, str, str]]:
    ids = set(flow.transition_ids or [])
    sigs: Set[Tuple[str, str, str, str]] = set()
    for t in pkg.transitions:
        if t.gt_transition_id not in ids:
            continue
        sigs.add(_tx_fingerprint(t.from_state_id, t.to_state_id, t.trigger_action_text, t.outcome_type))
    return sigs


def _pred_signatures_for_flow(
    predicted_rows: List[Dict[str, Any]],
    source_flow_id: str,
) -> Set[Tuple[str, str, str, str]]:
    sigs: Set[Tuple[str, str, str, str]] = set()
    for r in predicted_rows:
        if str(r.get("proposal_flow_id") or "").strip() != str(source_flow_id).strip():
            continue
        sigs.add(
            _tx_fingerprint(
                str(r.get("from_state_id") or ""),
                str(r.get("to_state_id") or ""),
                str(r.get("trigger_action_text") or ""),
                str(r.get("outcome_type") or ""),
            ),
        )
    return sigs


def _ordering_pair_score(gt_order: List[str], pred_order: List[str]) -> float:
    ids = [s for s in gt_order if s]
    if len(ids) < 2:
        return 1.0
    pos = {s: i for i, s in enumerate(pred_order) if s}
    total = 0
    correct = 0
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            total += 1
            a, b = ids[i], ids[j]
            if a in pos and b in pos and pos[a] < pos[b]:
                correct += 1
    return correct / total if total else 1.0


def _pred_order_for_flow(predicted_flows: List[Dict[str, Any]], source_flow_id: str) -> List[str]:
    for pf in predicted_flows:
        if str(pf.get("source_flow_id") or "").strip() == str(source_flow_id).strip():
            return list(pf.get("ordered_state_ids") or [])
    return []


def evaluate_flows(
    pkg: GroundTruthFlowPackage,
    predicted_rows: List[Dict[str, Any]],
    predicted_flows: List[Dict[str, Any]],
) -> List[FlowEvalItem]:
    items: List[FlowEvalItem] = []
    for fl in pkg.flows:
        if not getattr(fl, "eval_include", True):
            continue
        sid = str(fl.source_flow_id or "").strip()
        if not sid:
            continue
        gt_sig = _gt_flow_signatures(pkg, fl)
        pr_sig = _pred_signatures_for_flow(predicted_rows, sid)
        inter = gt_sig & pr_sig
        hits = len(inter)
        gt_only = len(gt_sig - inter)
        pred_only = len(pr_sig - inter)
        prec = len(inter) / len(pr_sig) if pr_sig else (1.0 if not gt_sig else 0.0)
        rec = len(inter) / len(gt_sig) if gt_sig else (1.0 if not pr_sig else 0.0)
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

        pred_order = _pred_order_for_flow(predicted_flows, sid)
        ord_acc = _ordering_pair_score(list(fl.ordered_state_ids or []), pred_order)

        err_tags: List[str] = []
        if pred_only:
            err_tags.append("extra_transition")
        if gt_only:
            err_tags.append("missing_transition")
        if ord_acc < 1.0:
            err_tags.append("wrong_ordering")

        items.append(
            FlowEvalItem(
                gt_flow_id=fl.gt_flow_id,
                pred_flow_id=sid,
                match_status="evaluated",
                member_transition_hits=hits,
                member_transition_misses=gt_only + pred_only,
                ordering_accuracy=ord_acc,
                membership_f1=f1,
                error_tags=err_tags,
            ),
        )
    return items
