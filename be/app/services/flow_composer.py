from __future__ import annotations
from app.services.intent_classifier import _aggregate_edges_confidence, _refine_flow_confidence_overall, _infer_intent_type, _expected_result_from_templates, _business_goal, _append_post_mapping_unresolved
import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.model_providers import model_adapter
import json
from app.constants.edge_taxonomy import (
    FATAL_EDGE_RISK_FLAGS,
    NON_SCENARIO_WORTHY_BRANCH_ROLES,
    SCENARIO_WORTHY_BRANCH_ROLES,
    default_scenario_branch_role,
)
from app.db.models.behaviour_intent import BehaviourIntent
from app.db.models.flow import Flow
from app.db.models.screen_intent import ScreenBehaviourIntent
from app.db.models.ui_element import UIElement
from app.model_providers.schemas import (
    BehaviourIntentA5,
    BehaviourIntentInferenceResult,
    ComposedFlowInternal,
    ComposedFlowSourceTraceStep,
    GenerationSummaryA5,
    TestDataRequirementA5,
    TriggerActionA5,
    UnresolvedFlowItemA5,
)
from app.services.test_path_utils import (
    map_test_path,
    format_action_step,
    select_distinguishing_evidence,
)
from app.services.flow_hydration_utils import (
    derive_trigger_from_edge,
    hydrate_flow_edges_for_compose,
)


def _merge_candidate_edge_row(
    candidate_edge_map: Dict[str, Dict[str, Any]], edge: Dict[str, Any]
) -> Dict[str, Any]:
    cid = edge.get("candidate_edge_id")
    base = dict(candidate_edge_map.get(str(cid), {})) if cid else {}
    return {**base, **edge}


def _is_scenario_worthy_branch_edge(
    candidate_edge_map: Dict[str, Dict[str, Any]],
    edge: Dict[str, Any],
) -> bool:
    m = _merge_candidate_edge_row(candidate_edge_map, edge)
    scope = str(m.get("action_scope") or "task_core")
    if scope in ("global_navigation", "local_chrome", "non_scenario_interaction"):
        return False
    thr = int(settings.CANDIDATE_EDGE_SCENARIO_WORTHINESS_MIN_FOR_AGENT4)
    sw = int(m.get("scenario_worthiness_score") or 100)
    if sw < thr:
        return False
    role = str(m.get("scenario_branch_role") or "")
    if not role:
        role = default_scenario_branch_role(str(m.get("edge_kind") or ""), "")
    if role in NON_SCENARIO_WORTHY_BRANCH_ROLES:
        return False
    if role not in SCENARIO_WORTHY_BRANCH_ROLES:
        return False
    if FATAL_EDGE_RISK_FLAGS.intersection(m.get("edge_risk_flags") or []):
        return False
    return True


def _flow_validation_status_for(flow_discovery_result: Dict[str, Any], source_flow_id: str) -> str:
    for f in flow_discovery_result.get("candidate_flows") or []:
        if str(f.get("flow_id") or "") == str(source_flow_id):
            return str(f.get("flow_validation_status") or "valid")
    return "valid"


def _build_node_map(state_catalog: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    node_map: Dict[str, Dict[str, Any]] = {}
    for state in state_catalog:
        keys = [
            state.get("canonical_state_id"),
            state.get("state_id"),
            state.get("source_state_id"),
            state.get("image_id"),
        ]
        for k in keys:
            if k:
                node_map[str(k)] = state
        for alias in state.get("aliases", []) or []:
            node_map[str(alias)] = state
    return node_map


def _edge_decisions_map(flow_discovery_result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for d in flow_discovery_result.get("edge_decisions") or []:
        if hasattr(d, "model_dump"):
            d = d.model_dump()
        eid = (d or {}).get("candidate_edge_id")
        if eid:
            out[str(eid)] = d
    return out


def _transition_dict_from_candidate(
    eid: str,
    edge_row: Dict[str, Any],
    tid_map: Mapping[str, str],
    *,
    orig_type: str = "transition",
) -> Dict[str, Any]:
    trig = derive_trigger_from_edge(edge_row)
    seq = edge_row.get("action_sequence") or []
    sg = seq[0].get("source_group_id") if seq else None
    si = seq[0].get("source_screen_intent_id") if seq else None
    base = {
        "from_state": edge_row["from_state"],
        "to_state": edge_row["to_state"],
        "relation_type": "direct_transition",
        "trigger_action": trig,
        "source_group_id": sg,
        "source_screen_intent_id": si,
        "candidate_edge_id": eid,
        "transition_id": tid_map.get(eid),
        "action_sequence": seq,
        "edge_kind": edge_row.get("edge_kind"),
        "_orig_type": orig_type,
    }
    if orig_type == "alternative":
        base["relation_type"] = "alternative_outcome"
        return {
            "source_state": edge_row["from_state"],
            "outcome_states": [edge_row["to_state"]],
            "trigger_action": trig,
            "relation_type": "alternative_outcome",
            "source_group_id": sg,
            "source_screen_intent_id": si,
            "candidate_edge_id": eid,
            "transition_id": tid_map.get(eid),
            "action_sequence": seq,
            "edge_kind": edge_row.get("edge_kind"),
            "_orig_type": "alternative",
        }
    return base


def _normalize_edge_shapes(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure from_state/to_state keys exist (legacy alternatives use source_state)."""
    if "from_state" in raw and raw["from_state"]:
        return raw
    src = raw.get("source_state")
    outs = raw.get("outcome_states") or []
    tgt = outs[0] if outs else ""
    merged = dict(raw)
    merged["from_state"], merged["to_state"] = src, tgt
    return merged


def _apply_edge_roles(
    e: Dict[str, Any],
    node_map: Dict[str, Dict[str, Any]],
    flow_id: str,
    flow_name: str,
) -> Optional[Dict[str, Any]]:
    e = _normalize_edge_shapes(dict(e))

    fs, ts = e.get("from_state"), e.get("to_state")
    if not fs or not ts:
        return None

    e["_source_flow_id"], e["_source_flow_name"] = flow_id, flow_name
    src_node, dst_node = node_map.get(str(fs), {}), node_map.get(str(ts), {})
    src_type = src_node.get("outcome_state_type", "neutral")
    dst_type = dst_node.get("outcome_state_type", "neutral")
    dst_presentation = (dst_node.get("presentation_scope") or "unknown").lower()

    ek = str(e.get("edge_kind") or "").lower()
    seq = e.get("action_sequence") or []
    has_nav_action = False
    for step in seq:
        if isinstance(step, dict):
            role = str(step.get("action_role") or "").lower()
        else:
            role = str(getattr(step, "action_role", "") or "").lower()
        if role in ("navigate", "support_navigation"):
            has_nav_action = True
            break

    is_support_nav = ("navigation" in ek or has_nav_action) and not (
        dst_type in ("success", "confirmation_required", "warning", "validation_error", "error")
    )

    if fs == ts:
        e["_role"] = "local_interaction"
    elif is_support_nav:
        e["_role"] = "support_navigation"
    elif src_type in ["success", "confirmation_required"]:
        e["_role"] = "post_success_navigation"
    elif dst_type in ["success", "confirmation_required"]:
        e["_role"] = "success_terminal"
    elif dst_type in ["warning", "validation_error", "error"] or e.get("relation_type") == "negative_outcome":
        e["_role"] = "negative_branch"
    elif dst_presentation in ["modal", "drawer", "popover"] or dst_type in [
        "modal",
        "cancellation_modal",
        "confirmation_modal",
    ]:
        e["_role"] = "modal_open"
    elif dst_type == "empty":
        e["_role"] = "empty_result"
    elif src_type == "review_required":
        e["_role"] = "review_commit"
    else:
        e["_role"] = "progress"

    e["target_visible_evidence"] = select_distinguishing_evidence(dst_node)

    if e["_role"] == "negative_branch" and dst_type == "warning":
        trig = e.get("trigger_action") if isinstance(e.get("trigger_action"), dict) else {}
        trigger_text = " ".join((trig or {}).get("text", []) or [])
        if _score_text_match(trigger_text, e["target_visible_evidence"]) < 0:
            return None

    return e


def _chain_is_continuous(edges: List[Dict[str, Any]]) -> bool:
    if not edges:
        return False
    for i in range(len(edges) - 1):
        if edges[i].get("to_state") != edges[i + 1].get("from_state"):
            return False
    return True


def _flow_type_and_name_for_branch(
    edge: Dict[str, Any],
    node_map: Dict[str, Dict[str, Any]],
) -> Tuple[str, str]:
    ts = edge.get("to_state") or ""
    dst = node_map.get(str(ts), {})
    dt = dst.get("outcome_state_type", "neutral")
    role = edge.get("_role", "")
    dk = str(edge.get("edge_kind") or "").lower()

    if role == "empty_result":
        return "empty_result_branch", "Empty result branch"

    if role == "support_navigation":
        if any(k in dk for k in ["retry", "recover"]):
            return "recovery_branch", "Recovery navigation"
        return "navigation_branch", "Support navigation"

    if dst.get("presentation_scope") and str(dst.get("presentation_scope")).lower() == "modal":
        if dt in ["cancellation_modal", "modal"]:
            return "cancellation_branch", "Cancellation / modal outcome"

    if role == "negative_branch":
        if dt == "validation_error" or dk == "validation_error":
            return "validation_branch", "Validation branch"
        if dt in ("warning", "error", "failure") or dk in ("warning", "error", "failure"):
            return "error_branch", "Error or warning outcome"
        return "validation_branch", "Negative branch outcome"

    if role == "modal_open" and dt == "confirmation_required":
        return "validation_branch", "Confirmation step outcome"

    if role == "modal_open":
        return "navigation_branch", "Modal navigation"

    if role == "success_terminal":
        return "navigation_branch", "Success-related transition"

    if role == "progress":
        return "navigation_branch", "Alternative path"

    return "navigation_branch", "Unclassified alternative branch"


def _main_path_flow_type(edge_sequence: List[Dict[str, Any]], node_map: Dict[str, Any]) -> str:
    """Main success journeys end in success-ish states (Agent 4 should only place core paths here)."""
    if not edge_sequence:
        return "main_success_path"
    last_node = node_map.get(str(edge_sequence[-1].get("to_state")), {})
    lt = last_node.get("outcome_state_type", "neutral")
    if lt in ("success", "confirmation_required"):
        return "main_success_path"
    if lt in ("error", "failure", "warning"):
        return "error_branch"
    if lt == "validation_error":
        return "validation_branch"
    if lt == "empty":
        return "empty_result_branch"
    if lt == "neutral" and edge_sequence[-1].get("_role") == "success_terminal":
        return "main_success_path"
    return "main_success_path"


def _source_trace_steps(
    edges: Sequence[Dict[str, Any]],
    decisions_map: Mapping[str, Dict[str, Any]],
) -> List[ComposedFlowSourceTraceStep]:
    trace: List[ComposedFlowSourceTraceStep] = []
    for e in edges:
        cid = str(e.get("candidate_edge_id") or "")
        d = decisions_map.get(cid, {})
        trace.append(
            ComposedFlowSourceTraceStep(
                candidate_edge_id=cid or None,
                transition_id=e.get("transition_id"),
                bucket=str(d.get("bucket") or "") or None,
                reason_code=str(d.get("reason_code") or "") or None,
            )
        )
    return trace


def _build_main_composed_flow_for_discovery_flow(
    flow: Dict[str, Any],
    candidate_edge_map: Dict[str, Dict[str, Any]],
    node_map: Dict[str, Dict[str, Any]],
    decisions_map: Dict[str, Dict[str, Any]],
    covered_edge_sigs: set[str],
    unresolved: List[UnresolvedFlowItemA5],
    flow_counters: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    flow_id = str(flow.get("flow_id") or "")
    flow_name = str(flow.get("flow_name") or flow_id or "flow")
    user_goal = str(flow.get("user_goal") or "")
    source_disc_flow_type = str(flow.get("flow_type") or "ordered_sequence")

    tid_map = flow.get("transition_id_by_candidate_edge_id") or {}

    transitions_h: List[Dict[str, Any]] = []

    use_edge_contract = bool(candidate_edge_map) and (
        "transition_edge_ids" in flow or "alternative_outcome_edge_ids" in flow
    )

    if use_edge_contract:
        transitions_h, _alternatives_h = hydrate_flow_edges_for_compose(flow, candidate_edge_map, tid_map)

        seq_ids = list(flow.get("transition_edge_ids") or [])
        path_edges_ordered: List[Dict[str, Any]] = []

        if seq_ids:
            missing: List[str] = []
            for eid in seq_ids:
                row = candidate_edge_map.get(str(eid))
                if not row:
                    missing.append(str(eid))
                    continue
                td = _transition_dict_from_candidate(str(eid), row, tid_map, orig_type="transition")
                en = _apply_edge_roles(td, node_map, flow_id, flow_name)
                if en is None:
                    continue
                if en.get("_role") in ("local_interaction", "support_navigation"):
                    continue
                path_edges_ordered.append(en)

            for mid in missing:
                unresolved.append(
                    UnresolvedFlowItemA5(
                        item_type="unsupported_transition",
                        source_id=mid,
                        related_states=[],
                        reason="transition_edge_ids references missing candidate edge",
                    )
                )

            if missing or not path_edges_ordered:
                unresolved.append(
                    UnresolvedFlowItemA5(
                        item_type="unsupported_flow",
                        source_id=flow_id,
                        related_states=list(flow.get("ordered_states") or []),
                        reason="transition_edge_ids could not be fully hydrated into edges; DFS fallback is disabled",
                    )
                )
                return None
            elif not _chain_is_continuous(path_edges_ordered):
                unresolved.append(
                    UnresolvedFlowItemA5(
                        item_type="unsupported_flow",
                        source_id=flow_id,
                        related_states=list(flow.get("ordered_states") or []),
                        reason="Agent 4 ordered transition edges do not form a continuous chain; DFS fallback is disabled",
                    )
                )
                return None

            method = "agent4_selected_edges"

        else:
            unresolved.append(
                UnresolvedFlowItemA5(
                    item_type="unsupported_flow",
                    source_id=flow_id,
                    related_states=list(flow.get("ordered_states") or []),
                    reason="candidate_flow has no transition_edge_ids and DFS fallback is disabled",
                )
            )
            return None

        # cover main-path edges
        for edge in path_edges_ordered:
            cid = edge.get("candidate_edge_id")
            if cid:
                covered_edge_sigs.add(f"edge:{cid}")
            else:
                covered_edge_sigs.add(f"{edge.get('from_state')}->{edge.get('to_state')}")

        state_path = [path_edges_ordered[0]["from_state"]] + [e["to_state"] for e in path_edges_ordered]
        ft = _main_path_flow_type(path_edges_ordered, node_map)
        conf, weak_hint = _aggregate_edges_confidence(path_edges_ordered, candidate_edge_map, decisions_map)
        conf = _refine_flow_confidence_overall(conf, ft, weak_hint)

        flow_counters.setdefault(flow_id, 0)
        flow_counters[flow_id] += 1
        suf = flow_counters[flow_id]

        last_e = path_edges_ordered[-1]
        cf = ComposedFlowInternal(
            composed_flow_id=f"cf_main_{flow_id}_{suf}",
            source_flow_id=flow_id,
            source_flow_name=flow_name,
            user_goal=user_goal,
            source_discovery_flow_type=source_disc_flow_type,
            flow_type=ft,
            start_state=str(state_path[0]),
            end_state=str(state_path[-1]),
            state_path=[str(s) for s in state_path],
            edge_sequence=path_edges_ordered,
            source_trace=_source_trace_steps(path_edges_ordered, decisions_map),
            composition_method=method,
            confidence=str(conf),
            behaviour_name=user_goal.strip() if user_goal.strip() else f"{flow_name} — main path",
            source_group_id=last_e.get("source_group_id"),
            source_screen_intent_id=last_e.get("source_screen_intent_id"),
        )
        return cf.model_dump()

    # Pre-candidate_edge discovery payloads: unsupported (composition requires transition_edge_ids)
    raw_transitions = list(flow.get("transitions") or [])
    if not raw_transitions:
        return None
    hydrated_any = False
    for t in raw_transitions:
        x = dict(t)
        x["_orig_type"] = "transition"
        en = _apply_edge_roles(_normalize_edge_shapes(x), node_map, flow_id, flow_name)
        if en:
            hydrated_any = True
            break
    if not hydrated_any:
        return None
    unresolved.append(
        UnresolvedFlowItemA5(
            item_type="unsupported_flow",
            source_id=flow_id,
            related_states=list(flow.get("ordered_states") or []),
            reason="Legacy flow shape requires DFS fallback which is permanently disabled",
        )
    )
    return None


def _all_classified_edges_union(
    flow_discovery_result: Dict[str, Any],
    candidate_edge_map: Dict[str, Dict[str, Any]],
    node_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Flatten candidate_flow edges after classification (branch discovery coverage)."""

    unique_edges: Dict[str, Dict[str, Any]] = {}
    for flow in flow_discovery_result.get("candidate_flows") or []:
        flow_id = str(flow.get("flow_id") or "")
        flow_name = str(flow.get("flow_name") or flow_id)

        raw_edges = []
        use_edge_contract = bool(candidate_edge_map) and (
            "transition_edge_ids" in flow or "alternative_outcome_edge_ids" in flow
        )
        tid_map = flow.get("transition_id_by_candidate_edge_id") or {}

        if use_edge_contract:
            transitions_h, alternatives_h = hydrate_flow_edges_for_compose(flow, candidate_edge_map, tid_map)
            for t in transitions_h:
                raw_edges.append(dict(t, _orig_type="transition"))
            for alt in alternatives_h:
                target = (alt.get("outcome_states") or [None])[0]
                if not target:
                    continue
                raw_edges.append(
                    {
                        "from_state": alt.get("source_state"),
                        "to_state": target,
                        "trigger_action": alt.get("trigger_action"),
                        "relation_type": alt.get("relation_type", "alternative_outcome"),
                        "source_group_id": alt.get("source_group_id"),
                        "source_screen_intent_id": alt.get("source_screen_intent_id"),
                        "candidate_edge_id": alt.get("candidate_edge_id"),
                        "transition_id": alt.get("transition_id"),
                        "action_sequence": alt.get("action_sequence"),
                        "edge_kind": alt.get("edge_kind"),
                        "_orig_type": "alternative",
                    }
                )
        else:
            for t in flow.get("transitions", []) or []:
                tt = dict(t)
                tt["_orig_type"] = "transition"
                raw_edges.append(tt)
            for alt in flow.get("alternative_outcomes", []) or []:
                target = (alt.get("outcome_states") or [None])[0]
                if not target:
                    continue
                raw_edges.append(
                    {
                        "from_state": alt.get("source_state"),
                        "to_state": target,
                        "trigger_action": alt.get("trigger_action"),
                        "relation_type": alt.get("relation_type", "alternative_outcome"),
                        "source_group_id": alt.get("source_group_id"),
                        "source_screen_intent_id": alt.get("source_screen_intent_id"),
                        "_orig_type": "alternative",
                    }
                )

        for e in raw_edges:
            en = _apply_edge_roles(_normalize_edge_shapes(dict(e)), node_map, flow_id, flow_name)
            if en is None:
                continue
            cid = str(en.get("candidate_edge_id") or "")
            key = (
                f"{en.get('from_state')}->{en.get('to_state')}@{cid}@"
                f"{''.join((en.get('trigger_action') or {}).get('text', []) or []).lower()}"
            )
            if key not in unique_edges:
                unique_edges[key] = en

    return list(unique_edges.values())


def _compose_flows_from_discovery(
    flow_discovery_result: Dict[str, Any],
    state_catalog: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[UnresolvedFlowItemA5], Dict[str, Any]]:
    node_map = _build_node_map(state_catalog)
    report = flow_discovery_result.get("report") or {}
    candidate_edges_list = report.get("candidate_edges") or []
    candidate_edge_map = {str(e["edge_id"]): dict(e) for e in candidate_edges_list if e.get("edge_id")}

    decisions_map = _edge_decisions_map(flow_discovery_result)

    composed: List[Dict[str, Any]] = []
    unresolved: List[UnresolvedFlowItemA5] = []
    covered_sig: set[str] = set()
    flow_ctr: Dict[str, int] = {}

    flows = flow_discovery_result.get("candidate_flows") or []
    if not flows:
        return [], unresolved, {"skipped_non_worthy_branch": 0}

    for flow in flows:
        cf_main = _build_main_composed_flow_for_discovery_flow(
            flow,
            candidate_edge_map,
            node_map,
            decisions_map,
            covered_sig,
            unresolved,
            flow_ctr,
        )
        if cf_main:
            composed.append(cf_main)

    filtered_edges = _all_classified_edges_union(flow_discovery_result, candidate_edge_map, node_map)

    flow_counters_alt: Dict[str, int] = {}

    dedupe_seen: set[Tuple[Any, Any, Any]] = set()
    skipped_non_worthy_branch = 0

    for edge in filtered_edges:
        if edge.get("_role") in ("post_success_navigation",):
            continue

        cid = edge.get("candidate_edge_id")
        edge_sig = f"edge:{cid}" if cid else f"{edge.get('from_state')}->{edge.get('to_state')}"
        if edge_sig in covered_sig:
            continue

        if not _is_scenario_worthy_branch_edge(candidate_edge_map, edge):
            skipped_non_worthy_branch += 1
            continue

        dedupe_key = (
            edge.get("from_state"),
            edge.get("to_state"),
            "".join((edge.get("trigger_action") or {}).get("text", []) or []).lower(),
            str(cid or ""),
        )
        if dedupe_key in dedupe_seen:
            continue
        dedupe_seen.add(dedupe_key)

        ft_detail, bn_base = _flow_type_and_name_for_branch(edge, node_map)
        flow_id_branch = str(edge.get("_source_flow_id") or "")
        flow_name_branch = str(edge.get("_source_flow_name") or flow_id_branch)
        ug = ""

        matched_flow = {}
        for f in flows:
            if str(f.get("flow_id")) == flow_id_branch:
                matched_flow = f
                ug = str(f.get("user_goal") or "")
                break
        sdisc = str(matched_flow.get("flow_type") or "branching_flow") if matched_flow else "branching_flow"

        ec = _aggregate_edges_confidence([edge], candidate_edge_map, decisions_map)[0]
        ec = _refine_flow_confidence_overall(ec, ft_detail, weak_evidence="low" == ec)

        flow_counters_alt.setdefault(flow_id_branch, 0)
        flow_counters_alt[flow_id_branch] += 1
        cid_part = cid or edge_sig.replace(":", "_")
        bf = ComposedFlowInternal(
            composed_flow_id=f"cf_branch_{flow_id_branch}_{cid_part}_{flow_counters_alt[flow_id_branch]}",
            source_flow_id=flow_id_branch,
            source_flow_name=flow_name_branch,
            user_goal=ug,
            source_discovery_flow_type=sdisc,
            flow_type=ft_detail,
            start_state=str(edge.get("from_state")),
            end_state=str(edge.get("to_state")),
            state_path=[str(edge.get("from_state")), str(edge.get("to_state"))],
            edge_sequence=[edge],
            source_trace=_source_trace_steps([edge], decisions_map),
            composition_method="agent4_selected_edges",
            confidence=str(ec),
            behaviour_name=f"{bn_base}: {edge.get('from_state')} → {edge.get('to_state')}",
            source_group_id=edge.get("source_group_id"),
            source_screen_intent_id=edge.get("source_screen_intent_id"),
        )
        composed.append(bf.model_dump())

    return composed, unresolved, {"skipped_non_worthy_branch": skipped_non_worthy_branch}


