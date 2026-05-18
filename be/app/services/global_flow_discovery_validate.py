"""Validate / repair structured output from batched global flow discovery."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from app.model_providers.schemas import (
    FlowDiscoveryAlternativeOutcome,
    FlowDiscoveryCandidateFlow,
    FlowDiscoveryEvidence,
    FlowDiscoverySemanticCluster,
    FlowDiscoveryStep,
    FlowDiscoveryTriggerAction,
    FlowDiscoveryUnassignedState,
    GlobalFlowDiscoveryResult,
    UncertainRelationGlobal,
)

NEGATIVE_SPINE_OUTCOMES = frozenset({"validation_error", "error", "warning"})
TERMINAL_STEP_ROLES = frozenset({"terminal_success", "terminal_failure"})
NEGATIVE_STEP_ROLES = frozenset({"outcome_validation", "outcome_error"})


def _norm_txt(s: str) -> str:
    return " ".join(str(s).lower().split())


def _taxonomy_outcome(state_row: Dict[str, Any]) -> str:
    tax = state_row.get("taxonomy") if isinstance(state_row, dict) else None
    if isinstance(tax, dict):
        return str(tax.get("outcome_state_type") or "")
    return ""


def _find_action_on_state(
    state_row: Dict[str, Any],
    *,
    intent_id: Optional[str],
    action_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    aid = str(action_id or "").strip()
    if not aid:
        return None, None

    iid_filter = str(intent_id).strip() if intent_id else ""

    for g in state_row.get("intent_groups") or []:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("intent_id") or "")
        if iid_filter and gid != iid_filter:
            continue
        pa = g.get("primary_action")
        if isinstance(pa, dict) and str(pa.get("action_id") or "").strip() == aid:
            return pa, gid or None

    return None, None


def _trigger_matches_catalog(state_row: Dict[str, Any], trig: FlowDiscoveryTriggerAction) -> bool:
    pa, _ = _find_action_on_state(state_row, intent_id=trig.intent_id, action_id=trig.action_id)
    if not isinstance(pa, dict):
        return False

    catalog_texts = [str(x) for x in (pa.get("text") or [])]
    llm_texts = list(trig.text or [])
    if not llm_texts:
        return True

    caps = {_norm_txt(t) for t in catalog_texts if t}
    joined = _norm_txt(" ".join(catalog_texts))

    for lt in llm_texts:
        n = _norm_txt(lt)
        if not n:
            continue
        if n in caps:
            continue
        if joined and (n == joined or n in joined):
            continue
        return False

    return True


def _sanitize_trigger(
    state_row: Dict[str, Any],
    trig: Optional[FlowDiscoveryTriggerAction],
    *,
    warnings: List[str],
    ctx: str,
) -> Optional[FlowDiscoveryTriggerAction]:
    if trig is None:
        return None
    pa, _ = _find_action_on_state(state_row, intent_id=trig.intent_id, action_id=trig.action_id)
    if not isinstance(pa, dict):
        warnings.append(f"{ctx}: nulled unknown trigger action_id={trig.action_id}")
        return None
    if not _trigger_matches_catalog(state_row, trig):
        warnings.append(f"{ctx}: repaired trigger text from catalogue for action_id={trig.action_id}")
        return FlowDiscoveryTriggerAction(
            intent_id=trig.intent_id,
            action_id=str(pa.get("action_id") or ""),
            action_type=str(pa.get("action_type") or ""),
            text=[str(x) for x in (pa.get("text") or [])],
        )
    return trig


def _collect_spine_state_sets(flows: List[FlowDiscoveryCandidateFlow]) -> Set[str]:
    states: Set[str] = set()
    for flow in flows:
        for st in flow.ordered_steps:
            sid = str(st.state_id or "").strip()
            if sid:
                states.add(sid)
    return states


def _collect_spine_edges(flows: List[FlowDiscoveryCandidateFlow]) -> Set[Tuple[str, str]]:
    edges: Set[Tuple[str, str]] = set()
    for flow in flows:
        steps = list(flow.ordered_steps)
        for j in range(len(steps) - 1):
            a = str(steps[j].state_id).strip()
            b = str(steps[j + 1].state_id).strip()
            if a and b:
                edges.add((a, b))
    return edges


def validate_discovery_output(
    parsed: GlobalFlowDiscoveryResult | Dict[str, Any],
    *,
    llm_catalog: Dict[str, Any],
) -> Dict[str, Any]:
    """Lightweight validation scan used for metrics (counts reflect LLM output before repair)."""

    model = parsed if isinstance(parsed, GlobalFlowDiscoveryResult) else GlobalFlowDiscoveryResult.model_validate(parsed)

    states_by_id: Dict[str, Dict[str, Any]] = {}
    for s in llm_catalog.get("states") or []:
        if isinstance(s, dict) and s.get("state_id"):
            states_by_id[str(s["state_id"])] = s

    valid_ids = set(states_by_id.keys())
    issues: List[str] = []
    invalid_state_refs = 0
    invalid_action_refs = 0

    def bump_state(msg: str) -> None:
        nonlocal invalid_state_refs
        invalid_state_refs += 1
        issues.append(msg)

    def bump_action(msg: str) -> None:
        nonlocal invalid_action_refs
        invalid_action_refs += 1
        issues.append(msg)

    for fi, flow in enumerate(model.candidate_flows):
        for si, st in enumerate(flow.ordered_steps):
            sid = str(st.state_id or "").strip()
            if sid and sid not in valid_ids:
                bump_state(f"candidate_flows[{fi}] step[{si}]: unknown state_id {sid}")
            trig = st.next_trigger_action
            if trig and sid in states_by_id:
                pa, _ = _find_action_on_state(states_by_id[sid], intent_id=trig.intent_id, action_id=trig.action_id)
                if not isinstance(pa, dict):
                    bump_action(f"candidate_flows[{fi}] step[{si}]: unknown action_id {trig.action_id} on {sid}")
                elif not _trigger_matches_catalog(states_by_id[sid], trig):
                    bump_action(f"candidate_flows[{fi}] step[{si}]: action text mismatch for {trig.action_id}")

        for ai, alt in enumerate(flow.alternative_outcomes):
            fs = str(alt.from_state_id or "").strip()
            ts = str(alt.to_state_id or "").strip()
            if fs and fs not in valid_ids:
                bump_state(f"candidate_flows[{fi}] alt[{ai}] unknown from_state_id {fs}")
            if ts and ts not in valid_ids:
                bump_state(f"candidate_flows[{fi}] alt[{ai}] unknown to_state_id {ts}")
            trig = alt.trigger_action
            if trig and fs in states_by_id:
                pa, _ = _find_action_on_state(states_by_id[fs], intent_id=trig.intent_id, action_id=trig.action_id)
                if not isinstance(pa, dict):
                    bump_action(f"candidate_flows[{fi}] alt[{ai}]: unknown action_id on {fs}")

    for ui, u in enumerate(model.unassigned_state_ids):
        sid = str(u.state_id or "").strip()
        if sid and sid not in valid_ids:
            bump_state(f"unassigned[{ui}]: unknown state_id {sid}")

    for ui, ur in enumerate(model.uncertain_relations):
        fr = ur.from_state_id
        to = ur.to_state_id
        if fr is not None and str(fr).strip() and str(fr) not in valid_ids:
            bump_state(f"uncertain[{ui}]: unknown from_state_id {fr}")
        if to is not None and str(to).strip() and str(to) not in valid_ids:
            bump_state(f"uncertain[{ui}]: unknown to_state_id {to}")

    return {
        "issues": issues,
        "invalid_state_ref_count": invalid_state_refs,
        "invalid_action_ref_count": invalid_action_refs,
    }


def repair_or_filter_discovery_output(
    parsed: GlobalFlowDiscoveryResult | Dict[str, Any],
    *,
    llm_catalog: Dict[str, Any],
) -> Tuple[GlobalFlowDiscoveryResult, List[str], Dict[str, Any]]:
    warnings: List[str] = []

    model = parsed if isinstance(parsed, GlobalFlowDiscoveryResult) else GlobalFlowDiscoveryResult.model_validate(parsed)

    states_by_id: Dict[str, Dict[str, Any]] = {}
    for s in llm_catalog.get("states") or []:
        if isinstance(s, dict) and s.get("state_id"):
            states_by_id[str(s["state_id"])] = s

    valid_ids = set(states_by_id.keys())

    preview = validate_discovery_output(model, llm_catalog=llm_catalog)

    repaired_clusters: List[FlowDiscoverySemanticCluster] = []
    for ci, cl in enumerate(model.semantic_clusters):
        obj = cl if isinstance(cl, FlowDiscoverySemanticCluster) else FlowDiscoverySemanticCluster.model_validate(cl)
        filt_states = [sid for sid in obj.state_ids if str(sid).strip() in valid_ids]
        dropped = len(obj.state_ids) - len(filt_states)
        if dropped:
            warnings.append(f"semantic_clusters[{ci}] {obj.cluster_id}: dropped {dropped} unknown state_ids")
        repaired_clusters.append(
            FlowDiscoverySemanticCluster(
                cluster_id=obj.cluster_id,
                cluster_goal=obj.cluster_goal,
                domain=obj.domain,
                state_ids=filt_states,
                cluster_evidence=list(obj.cluster_evidence),
            )
        )

    repaired_flows: List[FlowDiscoveryCandidateFlow] = []

    for fi, raw_flow in enumerate(model.candidate_flows):
        flow = raw_flow if isinstance(raw_flow, FlowDiscoveryCandidateFlow) else FlowDiscoveryCandidateFlow.model_validate(raw_flow)
        steps_in = list(flow.ordered_steps)
        filt_steps: List[FlowDiscoveryStep] = []

        for si, st in enumerate(steps_in):
            sid = str(st.state_id or "").strip()
            if not sid:
                warnings.append(f"candidate_flows[{fi}] step[{si}]: dropped empty state_id")
                continue
            if sid not in valid_ids:
                warnings.append(f"candidate_flows[{fi}] step[{si}]: dropped unknown state_id {sid}")
                continue
            if filt_steps and filt_steps[-1].state_id == sid:
                warnings.append(f"candidate_flows[{fi}]: collapsed duplicate consecutive step {sid}")
                continue

            row = states_by_id.get(sid, {})
            trig = _sanitize_trigger(
                row,
                st.next_trigger_action,
                warnings=warnings,
                ctx=f"candidate_flows[{fi}] step[{sid}]",
            )

            filt_steps.append(
                FlowDiscoveryStep(state_id=sid, step_role=st.step_role, next_trigger_action=trig)
            )

        filt_steps = _truncate_after_terminal(filt_steps, warnings, flow.flow_id)
        filt_steps = _strip_negative_interior_steps(filt_steps, states_by_id, warnings, flow.flow_id)

        alt_rep: List[FlowDiscoveryAlternativeOutcome] = []
        for ai, alt in enumerate(flow.alternative_outcomes):
            o = alt if isinstance(alt, FlowDiscoveryAlternativeOutcome) else FlowDiscoveryAlternativeOutcome.model_validate(alt)
            fs = str(o.from_state_id or "").strip()
            ts = str(o.to_state_id or "").strip()
            if fs not in valid_ids or ts not in valid_ids:
                warnings.append(f"candidate_flows[{fi}] alt[{ai}]: dropped unknown state refs")
                continue
            trig = _sanitize_trigger(
                states_by_id.get(fs, {}),
                o.trigger_action,
                warnings=warnings,
                ctx=f"candidate_flows[{fi}] alt {fs}->{ts}",
            )
            alt_rep.append(
                FlowDiscoveryAlternativeOutcome(
                    from_state_id=fs,
                    to_state_id=ts,
                    outcome_role=o.outcome_role,
                    trigger_action=trig,
                    evidence_summary=o.evidence_summary,
                )
            )

        evid_rep = [
            e if isinstance(e, FlowDiscoveryEvidence) else FlowDiscoveryEvidence.model_validate(e)
            for e in flow.flow_evidence
        ]

        if not filt_steps:
            warnings.append(f"candidate_flows[{fi}] {flow.flow_id}: dropped empty after validation")
            continue

        ft = str(flow.flow_type or "").strip()
        if ft == "ordered_sequence" and len(filt_steps) < 2:
            ft = "single_step_outcome"
            warnings.append(f"{flow.flow_id}: flow_type repaired ordered_sequence→single_step_outcome (too few states)")

        entry = str(flow.entry_state_id or filt_steps[0].state_id)

        repaired_flows.append(
            FlowDiscoveryCandidateFlow(
                flow_id=flow.flow_id,
                flow_name=flow.flow_name,
                flow_type=ft,  # type: ignore[arg-type]
                user_goal=str(flow.user_goal or flow.flow_name or "")[:500],
                flow_confidence=str(flow.flow_confidence or "medium"),
                ordered_steps=filt_steps,
                alternative_outcomes=alt_rep,
                flow_evidence=evid_rep,
                entry_state_id=entry,
                terminal_outcome=flow.terminal_outcome,
                rationale=str(flow.rationale or ""),
            )
        )

    spine_states = _collect_spine_state_sets(repaired_flows)
    spine_edges = _collect_spine_edges(repaired_flows)

    filt_unassigned: List[FlowDiscoveryUnassignedState] = []
    for u in model.unassigned_state_ids:
        obj = u if isinstance(u, FlowDiscoveryUnassignedState) else FlowDiscoveryUnassignedState.model_validate(u)
        sid = str(obj.state_id or "").strip()
        if not sid or sid not in valid_ids:
            warnings.append(f"unassigned: dropped unknown state_id {sid}")
            continue
        if sid in spine_states:
            warnings.append(f"unassigned: dropped {sid} (already on a flow spine)")
            continue
        filt_unassigned.append(obj)

    uncertain_rep: List[UncertainRelationGlobal] = []
    for ur in model.uncertain_relations:
        obj = ur if isinstance(ur, UncertainRelationGlobal) else UncertainRelationGlobal.model_validate(ur)
        fr = obj.from_state_id
        to = obj.to_state_id
        fs = str(fr or "").strip() if fr is not None else ""
        ts = str(to or "").strip() if to is not None else ""
        if fs and fs not in valid_ids:
            warnings.append(f"uncertain_relation dropped unknown from_state_id {fs}")
            continue
        if ts and ts not in valid_ids:
            warnings.append(f"uncertain_relation dropped unknown to_state_id {ts}")
            continue
        if fs and ts and (fs, ts) in spine_edges:
            warnings.append(f"uncertain_relation dropped duplicate spine edge {fs}->{ts}")
            continue
        uncertain_rep.append(obj)

    repaired = GlobalFlowDiscoveryResult(
        semantic_clusters=repaired_clusters,
        candidate_flows=repaired_flows,
        unassigned_state_ids=filt_unassigned,
        uncertain_relations=uncertain_rep,
        discovery_warnings=list(model.discovery_warnings),
    )

    repaired.discovery_warnings.extend(warnings)
    repaired.discovery_warnings = list(dict.fromkeys(repaired.discovery_warnings))

    post_any_issue = len(warnings) > 0 or preview["invalid_action_ref_count"] + preview["invalid_state_ref_count"] > 0

    metrics = {
        "invalid_state_ref_count_before_repair": preview["invalid_state_ref_count"],
        "invalid_action_ref_count_before_repair": preview["invalid_action_ref_count"],
        "post_validation_status": "repaired" if post_any_issue else "clean",
    }

    return repaired, metrics


def _truncate_after_terminal(steps: List[FlowDiscoveryStep], warnings: List[str], flow_id: str) -> List[FlowDiscoveryStep]:
    out: List[FlowDiscoveryStep] = []
    for st in steps:
        out.append(st)
        if str(st.step_role or "") in TERMINAL_STEP_ROLES:
            if len(out) < len(steps):
                warnings.append(f"{flow_id}: truncated spine after terminal step_role={st.step_role}")
            break
    return out


def _strip_negative_interior_steps(
    steps: List[FlowDiscoveryStep],
    states_by_id: Dict[str, Dict[str, Any]],
    warnings: List[str],
    flow_id: str,
) -> List[FlowDiscoveryStep]:
    if len(steps) <= 2:
        return steps

    kept: List[FlowDiscoveryStep] = [steps[0]]
    for i in range(1, len(steps) - 1):
        st = steps[i]
        sid = str(st.state_id).strip()
        ot = _taxonomy_outcome(states_by_id.get(sid, {}))
        role = str(st.step_role or "")
        if ot in NEGATIVE_SPINE_OUTCOMES or role in NEGATIVE_STEP_ROLES:
            warnings.append(f"{flow_id}: removed interior negative/outcome spine step {sid}")
            continue
        kept.append(st)
    kept.append(steps[-1])
    return kept


def validate_and_repair_global_flow_discovery(
    parsed: GlobalFlowDiscoveryResult | Dict[str, Any],
    *,
    llm_catalog: Dict[str, Any],
) -> Tuple[GlobalFlowDiscoveryResult, Dict[str, Any]]:
    """Entrypoint used by global_flow_discovery_service."""

    repaired, metrics = repair_or_filter_discovery_output(parsed, llm_catalog=llm_catalog)
    return repaired, metrics
