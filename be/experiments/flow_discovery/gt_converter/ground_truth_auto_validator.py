"""Structural + semantic checks on ground-truth draft (Sprint 4)."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Set

from experiments.flow_discovery.gt_converter import validation_helpers as vh
from experiments.flow_discovery.schemas.ground_truth_schema import (
    GroundTruthFlow,
    GroundTruthFlowPackage,
    GroundTruthTransition,
)


def _warn(code: str, message: str) -> Dict[str, Any]:
    return {"warning_code": code, "message": message}


def _flows_containing_transition(pkg: GroundTruthFlowPackage, gt_tx_id: str) -> List[GroundTruthFlow]:
    return [fl for fl in pkg.flows if gt_tx_id in (fl.transition_ids or [])]


def validate_transition(
    tx: GroundTruthTransition,
    pkg: GroundTruthFlowPackage,
    *,
    state_by_id: Dict[str, Any],
    fp_counts: Dict[Tuple[str, str, str, str], int],
) -> Dict[str, Any]:
    """Return transition ``auto_validation`` payload: checks + structured warnings."""

    warnings: List[Dict[str, Any]] = []

    src = state_by_id.get(tx.from_state_id)
    tgt = state_by_id.get(tx.to_state_id)
    state_refs_valid = src is not None and tgt is not None

    if not state_refs_valid:
        warnings.append(
            _warn(
                "STATE_REF_INVALID",
                f"Transition {tx.gt_transition_id} references unknown state(s): "
                f"from={tx.from_state_id}, to={tx.to_state_id}.",
            ),
        )

    trigger_id_ok = vh.trigger_action_id_known_on_source(pkg, tx.from_state_id, tx.trigger_action_id)
    if tx.trigger_action_id and str(tx.trigger_action_id).strip() and not trigger_id_ok:
        warnings.append(
            _warn(
                "TRIGGER_ACTION_ID_UNKNOWN_ON_SOURCE",
                f"Trigger action_id {tx.trigger_action_id!r} is not defined on source state {tx.from_state_id}.",
            ),
        )

    trigger_visible = state_refs_valid and vh.trigger_visible_on_source(pkg, src, tx)
    if state_refs_valid and not trigger_visible:
        src_label = getattr(src, "gt_state_id", tx.from_state_id)
        trig_label = tx.trigger_action_text or (tx.trigger_action_id or "")
        warnings.append(
            _warn(
                "TRIGGER_NOT_VISIBLE_ON_SOURCE",
                f"Trigger action {trig_label!r} is not visible on source state {src_label}.",
            ),
        )

    target_has_expected_evidence = True
    if tgt is not None and vh.state_has_visible_content(tgt) and not (tx.expected_visible_evidence or []):
        target_has_expected_evidence = False
        warnings.append(
            _warn(
                "TARGET_MISSING_EXPECTED_EVIDENCE",
                f"Target state {tgt.gt_state_id} has visible content but transition has empty expected_visible_evidence.",
            ),
        )

    validation_without_feedback = False
    if tgt is not None and vh.is_validation_like_outcome_type(getattr(tgt, "outcome_state_type", "") or ""):
        fb = getattr(tgt, "visible_evidence", None)
        has_fb = bool(fb and getattr(fb, "feedback", None))
        if not has_fb:
            validation_without_feedback = True
            warnings.append(
                _warn(
                    "VALIDATION_TARGET_WITHOUT_FEEDBACK",
                    "Target state is validation_error but no visible feedback was found.",
                ),
            )

    outcome_ok = vh.outcome_type_consistent(tx, tgt)
    if state_refs_valid and not outcome_ok:
        warnings.append(
            _warn(
                "OUTCOME_TYPE_MISMATCH_TARGET",
                f"outcome_type {tx.outcome_type!r} is inconsistent with target taxonomy "
                f"{getattr(tgt, 'outcome_state_type', '')!r}.",
            ),
        )

    fp = vh.transition_fingerprint(tx)
    dup = fp_counts.get(fp, 0) > 1
    if dup:
        warnings.append(
            _warn(
                "DUPLICATE_TRANSITION_DETECTED",
                f"Another transition shares the same endpoint/trigger/outcome fingerprint as {tx.gt_transition_id}.",
            ),
        )

    flow_chain_ok = True
    seen_flow_warn: set[str] = set()
    for fl in _flows_containing_transition(pkg, tx.gt_transition_id):
        if not vh.flow_chain_is_continuous(pkg, list(fl.ordered_state_ids or [])):
            flow_chain_ok = False
            if fl.gt_flow_id not in seen_flow_warn:
                seen_flow_warn.add(fl.gt_flow_id)
                warnings.append(
                    _warn(
                        "FLOW_CHAIN_NOT_CONTINUOUS",
                        f"Flow {fl.gt_flow_id} ordered states do not form a continuous transition path.",
                    ),
                )

    branch_ok = True
    for bg in pkg.branch_groups:
        if tx.gt_transition_id not in (bg.alternative_transition_ids or []):
            continue
        ntrig = vh.normalize_trigger_text(tx.trigger_action_text)
        expected_trig = str(bg.normalized_trigger or "").strip()
        if tx.from_state_id != bg.anchor_source_gt_state_id or (expected_trig and ntrig != expected_trig):
            branch_ok = False
            warnings.append(
                _warn(
                    "BRANCH_GROUP_INCONSISTENT",
                    f"Transition {tx.gt_transition_id} does not match branch group {bg.branch_group_id} anchor/trigger.",
                ),
            )

    checks = {
        "state_refs_valid": state_refs_valid,
        "trigger_action_visible_on_source": trigger_visible,
        "trigger_action_id_valid_if_present": trigger_id_ok,
        "target_has_expected_evidence": target_has_expected_evidence,
        "outcome_type_consistent_with_target": outcome_ok,
        "flow_chain_continuous": flow_chain_ok,
        "branch_group_consistent": branch_ok,
        # True if a duplicate fingerprint exists (problem); False when unique.
        "duplicate_transition_detected": dup,
    }

    return {"checks": checks, "warnings": warnings}


def _append_branch_group_target_warnings(pkg: GroundTruthFlowPackage, summary_codes: Counter[str], total_ref: list[int]) -> None:
    """Ensure groups with multiple alternatives branch to distinct target states."""

    for bg in pkg.branch_groups:
        alt_ids = list(bg.alternative_transition_ids or [])
        if len(alt_ids) < 2:
            continue
        tgt_ids: list[str] = []
        for tid in alt_ids:
            t2 = next((t for t in pkg.transitions if t.gt_transition_id == tid), None)
            if t2:
                tgt_ids.append(t2.to_state_id)
        if len(set(tgt_ids)) >= 2:
            continue
        for tid in alt_ids:
            tx = next((t for t in pkg.transitions if t.gt_transition_id == tid), None)
            if tx is None or not isinstance(tx.auto_validation, dict):
                continue
            w = _warn(
                "BRANCH_GROUP_INCONSISTENT",
                f"Branch group {bg.branch_group_id} lists multiple transitions but fewer than two distinct target states.",
            )
            tx.auto_validation.setdefault("warnings", []).append(w)
            ch = tx.auto_validation.setdefault("checks", {})
            ch["branch_group_consistent"] = False
            summary_codes[str(w["warning_code"])] += 1
            total_ref[0] += 1


def annotate_transition_validation(pkg: GroundTruthFlowPackage) -> None:
    state_by_id = vh.index_states_by_gt_id(pkg)
    fp_counts = vh.count_fingerprints(list(pkg.transitions))

    summary_codes: Counter[str] = Counter()
    total_warnings = 0

    for tx in pkg.transitions:
        payload = validate_transition(tx, pkg, state_by_id=state_by_id, fp_counts=fp_counts)
        tx.auto_validation = payload
        for w in payload.get("warnings") or []:
            code = str(w.get("warning_code") or "UNKNOWN")
            summary_codes[code] += 1
            total_warnings += 1

    total_ref = [total_warnings]
    _append_branch_group_target_warnings(pkg, summary_codes, total_ref)
    total_warnings = total_ref[0]

    pkg.package_auto_validation.extras["warning_summary_by_code"] = dict(summary_codes)
    pkg.package_auto_validation.extras["transition_warning_count"] = total_warnings


def annotate_package_issues(pkg: GroundTruthFlowPackage) -> GroundTruthFlowPackage:
    """Mutate ``package_auto_validation`` with structural warnings + per-transition validation."""

    blk = pkg.package_auto_validation
    blk.warnings.clear()
    blk.flags.clear()
    blk.extras.pop("warning_summary_by_code", None)
    blk.extras.pop("transition_warning_count", None)

    for tx in pkg.transitions:
        tx.auto_validation = {}

    warnings: list[str] = []
    flags: list[str] = []

    gt_state_ids = {s.gt_state_id for s in pkg.states}

    txn_ids_seen: Set[str] = set()
    for tx in pkg.transitions:
        if tx.gt_transition_id in txn_ids_seen:
            warnings.append(f"duplicate_gt_transition_id:{tx.gt_transition_id}")
            flags.append("duplicate_transition_id")
        txn_ids_seen.add(tx.gt_transition_id)
        if tx.from_state_id not in gt_state_ids:
            warnings.append(f"transition_orphan_source:{tx.gt_transition_id}")
            flags.append("orphan_transition_refs")
        if tx.to_state_id not in gt_state_ids:
            warnings.append(f"transition_orphan_target:{tx.gt_transition_id}")
            flags.append("orphan_transition_refs")

    gt_action_parents = {a.source_state_gt_id for a in pkg.actions}
    for gid in gt_action_parents:
        if gid and gid not in gt_state_ids:
            warnings.append(f"action_unknown_state_reference:{gid}")
            flags.append("orphan_action_state")

    for fl in pkg.flows:
        for sid in (
            *fl.ordered_state_ids,
            getattr(fl, "entry_state_id", ""),
            getattr(fl, "terminal_state_id", ""),
        ):
            if sid and sid not in gt_state_ids:
                warnings.append(f"flow_unknown_state_id:{sid}")
                flags.append("orphan_flow_refs")
        tid_set = {t.gt_transition_id for t in pkg.transitions}
        for tid in getattr(fl, "transition_ids") or []:
            if tid and tid not in tid_set:
                warnings.append(f"flow_unknown_transition_id:{tid}:{fl.gt_flow_id}")
                flags.append("orphan_transition_flow")

    blk = pkg.package_auto_validation
    blk.warnings.extend(warnings)
    blk.flags.extend(flags)

    annotate_transition_validation(pkg)

    if blk.extras.get("transition_warning_count", 0):
        blk.flags.append("transition_semantic_warnings")

    return pkg
