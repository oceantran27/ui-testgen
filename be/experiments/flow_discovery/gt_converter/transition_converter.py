"""Transitions from repaired ``GlobalFlowDiscoveryResult`` (ordered_steps + alternatives)."""

from __future__ import annotations

from typing import Any, Dict, List

from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthTransition


PROPOSAL_SPINE = "raw_model_output.ordered_steps"
PROPOSAL_ALT = "raw_model_output.alternative_outcomes"


def _trigger_from_dict(trig: Any) -> tuple[str | None, str]:
    if not isinstance(trig, dict):
        return None, ""
    texts = trig.get("text")
    txt = ""
    if isinstance(texts, list):
        txt = " ".join(str(x).strip() for x in texts if str(x).strip())
    elif isinstance(texts, str):
        txt = texts.strip()
    aid = str(trig.get("action_id") or "").strip() or None
    return aid, txt


def _combine_target_evidence(target_card: Dict[str, Any]) -> List[str]:
    from experiments.flow_discovery.gt_converter.state_converter import _bucket_visible_evidence

    ev = _bucket_visible_evidence(target_card)
    out: List[str] = []
    out.extend(ev.headings)
    out.extend(ev.texts[:8])
    if not out:
        out.extend(ev.actions[:4])
        out.extend(ev.feedback[:4])
    seen: set[str] = set()
    uniq: List[str] = []
    for item in out:
        k = item.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(item)
    return uniq[:12]


def _merge_outcome(taxonomy: Dict[str, Any], alt_role: str) -> str:
    base = str(taxonomy.get("outcome_state_type") or "neutral").strip().lower()
    role = str(alt_role or "").strip().lower()
    if role in ("success",):
        return "success"
    if role in ("validation_error",):
        return base if base else "validation_error"
    if role in ("error", "fatal", "failure"):
        return "error"
    if role in ("cancelled", "cancel", "dismiss"):
        return "cancellation_branch"
    if role in ("modal", "overlay"):
        return "modal_branch"
    if role in ("neutral", ""):
        return base if base else "neutral"
    return role if role else base


def build_transitions(
    app_id: str,
    model_dict: Dict[str, Any],
    catalog_to_gt: Dict[str, str],
    card_by_catalog_id: Dict[str, Dict[str, Any]],
) -> List[GroundTruthTransition]:
    """Produce spine plus alternative transitions for each candidate flow."""

    txs: List[GroundTruthTransition] = []
    tctr = 0

    flows = model_dict.get("candidate_flows") or []
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        flow_id = str(flow.get("flow_id") or "unknown_flow")

        steps = flow.get("ordered_steps") or []
        for i in range(len(steps) - 1):
            a_step = steps[i]
            b_step = steps[i + 1]
            if not isinstance(a_step, dict) or not isinstance(b_step, dict):
                continue
            from_c = str(a_step.get("state_id") or "").strip()
            to_c = str(b_step.get("state_id") or "").strip()
            if not from_c or not to_c:
                continue
            if from_c not in catalog_to_gt or to_c not in catalog_to_gt:
                continue
            trig_obj = (a_step or {}).get("next_trigger_action")
            aid, ttext = _trigger_from_dict(trig_obj)

            tgt = card_by_catalog_id.get(to_c, {})
            tax = dict((tgt.get("taxonomy") or {}))
            outcome = _merge_outcome(tax, "")
            evidence = _combine_target_evidence(tgt)

            slug = f"{_slug_piece(from_c)}_{_slug_piece(to_c)}_{_slug_piece(ttext)}_{tctr}".strip("_")[:72]
            gt_tx_id = f"gt_t_{app_id}_{slug}"
            tctr += 1
            txs.append(
                GroundTruthTransition(
                    gt_transition_id=gt_tx_id,
                    from_state_id=catalog_to_gt[from_c],
                    to_state_id=catalog_to_gt[to_c],
                    trigger_action_id=aid,
                    trigger_action_text=ttext or "",
                    outcome_type=outcome,
                    expected_visible_evidence=evidence,
                    proposal_source=PROPOSAL_SPINE,
                    proposal_flow_id=flow_id,
                    proposal_confidence=str(flow.get("flow_confidence") or flow.get("confidence") or "") or None,
                )
            )

        for alt in flow.get("alternative_outcomes") or []:
            if not isinstance(alt, dict):
                continue
            from_c = str(alt.get("from_state_id") or "").strip()
            to_c = str(alt.get("to_state_id") or "").strip()
            if not from_c or not to_c:
                continue
            if from_c not in catalog_to_gt or to_c not in catalog_to_gt:
                continue
            trig_obj = alt.get("trigger_action")
            aid, ttext = _trigger_from_dict(trig_obj)

            tgt = card_by_catalog_id.get(to_c, {})
            tax = dict((tgt.get("taxonomy") or {}))
            role = str(alt.get("outcome_role") or "")
            outcome = _merge_outcome(tax, role)
            evidence = _combine_target_evidence(tgt)

            slug = f"alt_{_slug_piece(from_c)}_{_slug_piece(to_c)}_{_slug_piece(role)}_{tctr}".strip("_")[:72]
            gt_tx_id = f"gt_t_{app_id}_{slug}"
            tctr += 1
            txs.append(
                GroundTruthTransition(
                    gt_transition_id=gt_tx_id,
                    from_state_id=catalog_to_gt[from_c],
                    to_state_id=catalog_to_gt[to_c],
                    trigger_action_id=aid,
                    trigger_action_text=ttext or "",
                    outcome_type=outcome,
                    expected_visible_evidence=evidence,
                    proposal_source=PROPOSAL_ALT,
                    proposal_flow_id=flow_id,
                )
            )

    return txs


def _slug_piece(s: str) -> str:
    s = str(s or "").lower().replace(" ", "_")
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_")[:24] or "x"


def _normalize_trigger(text: str) -> str:
    return " ".join(str(text).lower().split())


def transitions_by_branch_key(transitions: List[GroundTruthTransition]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for tx in transitions:
        key = f"{tx.from_state_id}||{_normalize_trigger(tx.trigger_action_text)}"
        out.setdefault(key, []).append(tx.gt_transition_id)
    return out
