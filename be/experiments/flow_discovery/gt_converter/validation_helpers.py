"""Deterministic helpers for ground-truth draft validation (Sprint 4)."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from experiments.flow_discovery.schemas.ground_truth_schema import (
    GroundTruthAction,
    GroundTruthFlowPackage,
    GroundTruthState,
    GroundTruthTransition,
)


def normalize_trigger_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def transition_fingerprint(tx: GroundTruthTransition) -> Tuple[str, str, str, str]:
    return (
        tx.from_state_id,
        tx.to_state_id,
        normalize_trigger_text(tx.trigger_action_text),
        str(tx.outcome_type or "").strip().lower(),
    )


def index_states_by_gt_id(pkg: GroundTruthFlowPackage) -> Dict[str, GroundTruthState]:
    return {s.gt_state_id: s for s in pkg.states}


def actions_for_source_state(pkg: GroundTruthFlowPackage, source_gt_id: str) -> List[GroundTruthAction]:
    return [a for a in pkg.actions if a.source_state_gt_id == source_gt_id]


def trigger_action_id_known_on_source(pkg: GroundTruthFlowPackage, source_gt_id: str, action_id: Optional[str]) -> bool:
    if not action_id or not str(action_id).strip():
        return True
    aid = str(action_id).strip()
    for a in actions_for_source_state(pkg, source_gt_id):
        if str(a.system_action_id or "").strip() == aid:
            return True
    return False


def _norm_set(labels: Iterable[str]) -> Set[str]:
    return {normalize_trigger_text(x) for x in labels if str(x).strip()}


def trigger_text_visible_on_source_state(source: GroundTruthState, trigger_text: str) -> bool:
    norm = normalize_trigger_text(trigger_text)
    if not norm:
        return False
    v = source.visible_evidence
    caps = _norm_set(v.actions) | _norm_set(v.headings) | _norm_set(v.texts)
    for c in caps:
        if not c:
            continue
        if norm == c or norm in c or c in norm:
            return True
    return False


def trigger_visible_on_source(
    pkg: GroundTruthFlowPackage,
    source: Optional[GroundTruthState],
    tx: GroundTruthTransition,
) -> bool:
    if source is None:
        return False
    aid = str(tx.trigger_action_id or "").strip()
    txt = normalize_trigger_text(tx.trigger_action_text)
    if aid:
        if not trigger_action_id_known_on_source(pkg, source.gt_state_id, aid):
            return False
        acts = actions_for_source_state(pkg, source.gt_state_id)
        matched = [a for a in acts if str(a.system_action_id or "").strip() == aid]
        if not matched:
            return False
        a0 = matched[0]
        cat_norms = {normalize_trigger_text(a0.action_text)} | _norm_set([a0.action_text])
        cat_norms.discard("")
        if not txt:
            return True
        if not cat_norms:
            return trigger_text_visible_on_source_state(source, tx.trigger_action_text)
        for cn in cat_norms:
            if cn and (txt == cn or txt in cn or cn in txt):
                return True
        return trigger_text_visible_on_source_state(source, tx.trigger_action_text)
    return trigger_text_visible_on_source_state(source, tx.trigger_action_text)


def state_has_visible_content(state: Optional[GroundTruthState]) -> bool:
    if state is None:
        return False
    v = state.visible_evidence
    return bool(v.headings or v.texts or v.feedback)


def is_validation_like_outcome_type(ost: str) -> bool:
    o = str(ost or "").strip().lower()
    return o in (
        "validation_error",
        "validation_blocked",
        "invalid_input",
    ) or "validation" in o


def expected_transition_outcome_from_target(target: Optional[GroundTruthState], fallback_outcome: str) -> str:
    if target is None:
        return str(fallback_outcome or "").strip().lower()
    ost = str(target.outcome_state_type or "").strip().lower()
    if ost in ("positive", "success", "complete", "done"):
        return "success"
    if is_validation_like_outcome_type(ost):
        return "validation_error"
    if ost in ("error", "negative", "failure", "fatal"):
        return "error"
    if ost in ("neutral", ""):
        return str(fallback_outcome or "neutral").strip().lower() or "neutral"
    return ost if ost else str(fallback_outcome or "").strip().lower()


def outcome_type_consistent(tx: GroundTruthTransition, target: Optional[GroundTruthState]) -> bool:
    expected = expected_transition_outcome_from_target(target, tx.outcome_type)
    actual = str(tx.outcome_type or "").strip().lower()
    if expected == actual:
        return True
    if expected in ("neutral", "") and actual in ("neutral", "success"):
        return True
    if expected == "success" and actual in ("neutral", "modal_branch"):
        return True
    return False


def pair_has_transition(pkg: GroundTruthFlowPackage, from_id: str, to_id: str) -> bool:
    for t in pkg.transitions:
        if t.from_state_id == from_id and t.to_state_id == to_id:
            return True
    return False


def flow_chain_is_continuous(pkg: GroundTruthFlowPackage, flow_ordered_state_ids: List[str]) -> bool:
    ids = [s for s in flow_ordered_state_ids if s]
    if len(ids) < 2:
        return True
    for i in range(len(ids) - 1):
        if not pair_has_transition(pkg, ids[i], ids[i + 1]):
            return False
    return True


def count_fingerprints(transitions: List[GroundTruthTransition]) -> Dict[Tuple[str, str, str, str], int]:
    counts: Dict[Tuple[str, str, str, str], int] = defaultdict(int)
    for tx in transitions:
        counts[transition_fingerprint(tx)] += 1
    return counts


def transitions_by_flow_id(pkg: GroundTruthFlowPackage) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = defaultdict(list)
    for tx in pkg.transitions:
        fid = tx.proposal_flow_id
        if fid:
            out[str(fid)].append(tx.gt_transition_id)
    return dict(out)
