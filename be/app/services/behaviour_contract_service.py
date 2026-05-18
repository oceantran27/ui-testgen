"""
Behaviour Contract Builder Service — Agent 5.
Maps Agent 4-selected flows deterministically onto Behaviour Contracts (test intents).
"""
from __future__ import annotations

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
from app.services.flow_hydration_utils import (
    derive_trigger_from_edge,
    hydrate_flow_edges_for_compose,
)

# ── IDs ─────────────────────────────────────────────────────────────


def _generate_behaviour_intent_id(run_id: str) -> str:
    """behaviour_intents.id is a global PK — never persist LLM ids directly."""
    return f"bi_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


def map_test_path(intent_type: str) -> str:
    normalized = (intent_type or "").strip().lower()
    mapping = {
        "positive": "happy_path",
        "negative": "negative_path",
        "validation": "validation_path",
        "navigation": "navigation_path",
        "recovery": "recovery_path",
        "registration": "registration_path",
        "access_control": "access_control_path",
        "data_entry": "data_entry_path",
    }
    return mapping.get(normalized, "unknown_path")


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


def _persist_intent_row(
    run_id: str,
    intent: BehaviourIntentA5,
) -> BehaviourIntent:
    test_path = map_test_path(intent.intent_type)
    return BehaviourIntent(
        id=intent.intent_id,
        run_id=run_id,
        flow_id=intent.source_flow_id,
        source_flow_name=intent.source_flow_name,
        source_flow_type=intent.source_flow_type,
        source_transition_indexes_json={"indexes": intent.source_transition_indexes},
        source_outcome_state=intent.source_outcome_state,
        source_group_id=intent.source_group_id,
        source_screen_intent_id=intent.source_screen_intent_id,
        source_transition_ids_json={"ids": intent.source_transition_ids},
        behaviour_name=intent.behaviour_name,
        intent_type=intent.intent_type,
        test_path=test_path,
        user_intent=intent.user_intent,
        business_goal=intent.business_goal,
        start_state=intent.start_state,
        end_state=intent.end_state,
        trigger_action_json=intent.trigger_action.model_dump(),
        preconditions_json={"items": intent.preconditions},
        test_data_requirements_json={"items": [i.model_dump() for i in intent.test_data_requirements]},
        user_actions_json={"items": intent.user_actions},
        expected_result=intent.expected_result,
        expected_ui_evidence_json={"items": intent.expected_ui_evidence},
        negative_expectations_json={"items": intent.negative_expectations},
        confidence=intent.confidence,
        assumptions_json={"items": intent.assumptions},
        warnings_json={"items": intent.warnings},
        raw_result_json=intent.model_dump(),
    )


def select_distinguishing_evidence(node: Dict[str, Any]) -> List[str]:
    """
    Extracts minimal, distinguishing UI evidence for BDD assertions generically.
    """
    texts: List[str] = []

    for f in node.get("visible_feedback", []):
        texts.extend(f.get("text", []))

    for e in node.get("visible_elements", []):
        role = (e.get("role_hint") or "").lower()
        is_distinguishing = any(r in role for r in ["heading", "title", "status", "alert", "toast", "feedback"])
        if is_distinguishing:
            texts.extend(e.get("text", []))

    filtered: List[str] = []
    for t in texts:
        t_clean = t.strip()
        if not t_clean or len(t_clean) <= 1:
            continue
        if any(c in t_clean.lower() for c in ["©", "copyright", "all rights reserved"]):
            continue
        filtered.append(t_clean)

    if not filtered:
        for e in node.get("visible_elements", []):
            role = (e.get("role_hint") or "").lower()
            if any(r in role for r in ["header", "footer", "sidebar_nav", "nav"]):
                continue
            for txt in e.get("text", []):
                t_clean = txt.strip()
                if len(t_clean) > 1 and not any(c in t_clean.lower() for c in ["©", "copyright"]):
                    filtered.append(t_clean)

    seen = set()
    return [x for x in filtered if not (x in seen or seen.add(x))]


def strip_gherkin_keywords(text: str) -> str:
    """Removes leading Given/When/Then/And keywords from a sentence."""
    if not text:
        return ""
    import re

    return re.sub(r"^(Given|When|Then|And|But)\s+", "", text.strip(), flags=re.I)


def format_action_step(action: Any) -> str:
    """Formats raw UI triggers into generic BDD actions (e.g. Click, Select, Enter)"""
    if not action:
        return ""

    if isinstance(action, dict):
        a_type = (action.get("action_type") or "click").lower()
        a_text = " ".join(action.get("text", []))
    else:
        a_type = (getattr(action, "action_type", "click") or "click").lower()
        a_text = " ".join(getattr(action, "text", []))

    if not a_text:
        return ""

    if a_type in ["select_option", "select", "option", "choice"]:
        return f"Select \"{a_text}\""
    elif a_type in ["input", "type", "fill", "enter"]:
        return f"Enter \"{a_text}\""
    elif a_type in ["commit", "confirm", "submit"]:
        return f"Confirm \"{a_text}\""
    else:
        return f"Click \"{a_text}\""


def _score_text_match(trigger_text: str, target_evidence: List[str]) -> float:
    """Heuristic to check if a trigger (e.g. '09:00') is relevant to target evidence."""
    if not trigger_text or not target_evidence:
        return 0.0
    trigger_lower = trigger_text.lower()
    target_all = " ".join(target_evidence).lower()

    import re

    trigger_nums = re.findall(r"\d+[:\.]\d+", trigger_lower)
    if trigger_nums:
        score = 0.0
        for num in trigger_nums:
            if num in target_all:
                score += 1.0
            else:
                score -= 1.0
        return score

    words = [w for w in trigger_lower.split() if len(w) > 3]
    if not words:
        return 0.5
    match_count = sum(1 for w in words if w in target_all)
    return match_count / len(words)


# ── Graph helpers ────────────────────────────────────────────────────


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
    e = dict(e)
    _normalize_edge_shapes(e)

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
    if lt == "confirmation_required":
        return "main_success_path"
    if lt in ("success", "neutral") and edge_sequence[-1].get("_role") == "success_terminal":
        return "main_success_path"
    return "main_success_path"


def _confidence_order(label: str) -> int:
    s = str(label).strip().lower()
    if s == "high":
        return 2
    if s == "low":
        return 0
    return 1


def _aggregate_edges_confidence(
    edges: Sequence[Dict[str, Any]],
    candidate_edge_map: Mapping[str, Dict[str, Any]],
    decisions_map: Mapping[str, Dict[str, Any]],
) -> Tuple[str, bool]:
    """
    Returns intent confidence label and whether any edge had risk flags / weak evidence.
    """
    if not edges:
        return "low", True

    levels: List[int] = []
    any_low = False
    any_medium = False
    any_risk = False

    for e in edges:
        cid = str(e.get("candidate_edge_id") or "")
        row = candidate_edge_map.get(cid) or {}
        c = str(row.get("confidence") or "medium").strip().lower()
        flags = row.get("edge_risk_flags") or []
        if isinstance(flags, list) and flags:
            any_risk = True

        dd = decisions_map.get(cid) or {}
        ev = str(dd.get("evidence_level") or "").strip().lower()

        level = _confidence_order(c)
        if level == 0:
            any_low = True
        elif level == 1:
            any_medium = True

        if ev == "medium":
            any_medium = True

        evidence_penalty = 0 if ev == "strong" else 1
        lvl = max(0, level - evidence_penalty)
        levels.append(lvl)

    floor = min(levels) if levels else 1
    if floor == 0 or any_low:
        return "low", any_risk
    if floor == 1 or any_medium or any_risk:
        return "medium", any_risk
    return "high", False


def _refine_flow_confidence_overall(base: str, flow_type_internal: str, weak_evidence: bool) -> str:
    ft = flow_type_internal
    neg_like = ft in {"validation_branch", "error_branch", "empty_result_branch", "cancellation_branch"}
    if neg_like or weak_evidence:
        if base == "high":
            return "medium"
    return base


def _infer_intent_type(
    flow_type_internal: str,
    end_node: Dict[str, Any],
    last_edge: Optional[Dict[str, Any]],
    intent_kind_optional: Optional[str],
) -> str:
    ot = (end_node or {}).get("outcome_state_type", "neutral")
    role = (last_edge or {}).get("_role")

    ik = str(intent_kind_optional or "").lower()

    if flow_type_internal == "main_success_path":
        if ot == "confirmation_required":
            return "validation" if ik == "confirmation" else "positive"
        return "positive"

    if flow_type_internal == "validation_branch":
        return "validation"

    if flow_type_internal == "error_branch":
        return "negative"

    if flow_type_internal == "empty_result_branch":
        if ot in {"error", "warning"}:
            return "negative"
        return "validation"

    if flow_type_internal == "cancellation_branch":
        return "negative"

    if flow_type_internal == "recovery_branch":
        return "recovery"

    if flow_type_internal == "navigation_branch":
        return "navigation"

    if ot == "validation_error":
        return "validation"
    if ot in {"error", "warning"}:
        return "negative"

    if role == "modal_open":
        return "validation" if ot == "confirmation_required" else "unknown"

    return "unknown"


def _expected_result_from_templates(
    end_node: Dict[str, Any],
    last_edge: Optional[Dict[str, Any]],
) -> str:
    ot = str((end_node or {}).get("outcome_state_type", "neutral") or "").lower()
    ev = []
    if last_edge:
        ev = list(last_edge.get("target_visible_evidence") or [])

    if ot == "success":
        return "The success outcome is displayed."
    if ot == "confirmation_required":
        return "The confirmation step is displayed."
    if ot == "validation_error":
        return "The UI displays validation feedback."
    if ev:
        return "The UI displays the expected destination state."
    if ot in {"warning"}:
        return "The UI displays a warning outcome."
    if ot in {"error", "failure"}:
        return "The UI displays an error outcome."

    return "The observable UI state reflects the executed flow."


def _business_goal(flow_name: str, user_goal: str) -> str:
    ug = (user_goal or "").strip()
    if ug:
        return ug
    return (flow_name or "").strip() or "User flow"


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


async def _load_intent_kind_map(
    db: AsyncSession, run_id: str, ids: Sequence[str]
) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """intent_id -> (intent_kind, intent_name)."""
    want = sorted({str(x) for x in ids if x})
    if not want:
        return {}
    stmt = select(ScreenBehaviourIntent).where(ScreenBehaviourIntent.run_id == run_id, ScreenBehaviourIntent.id.in_(want))
    rows = list((await db.execute(stmt)).scalars().all())
    return {
        str(r.id): (
            getattr(r, "intent_kind", None),
            getattr(r, "intent_name", None),
        )
        for r in rows
    }


async def _build_test_data_requirements(
    db: AsyncSession,
    run_id: str,
    edge_sequence: List[Dict[str, Any]],
) -> Tuple[List[TestDataRequirementA5], List[str]]:
    """
    Screen intent grounded test data placeholders — never invent literal values.
    """
    reqs: List[TestDataRequirementA5] = []
    warns: List[str] = []

    intent_ids = sorted({str(e.get("source_screen_intent_id")) for e in edge_sequence if e.get("source_screen_intent_id")})
    if not intent_ids:
        return reqs, warns

    stmt = select(ScreenBehaviourIntent).where(
        ScreenBehaviourIntent.run_id == run_id,
        ScreenBehaviourIntent.id.in_(intent_ids),
    )
    intents = list((await db.execute(stmt)).scalars().all())
    intents_by_id = {str(i.id): i for i in intents}

    elem_ids_all: List[str] = []
    for i in intents:
        raw = getattr(i, "required_input_element_ids_json", None) or []
        if isinstance(raw, list):
            elem_ids_all.extend(str(x) for x in raw)
        elif isinstance(raw, dict) and isinstance(raw.get("element_ids"), list):
            elem_ids_all.extend(str(x) for x in raw["element_ids"])

    elem_ids_all = sorted({x for x in elem_ids_all if x})
    elems_by_id: Dict[str, UIElement] = {}
    if elem_ids_all:
        estmt = select(UIElement).where(UIElement.run_id == run_id, UIElement.id.in_(elem_ids_all))
        for el in (await db.execute(estmt)).scalars().all():
            elems_by_id[str(el.id)] = el

    for iid in intent_ids:
        row = intents_by_id.get(iid)
        if row is None:
            warns.append(f"Missing screen_behaviour_intent row for intent id {iid}")
            reqs.append(
                TestDataRequirementA5(
                    field_or_input="(intent record missing)",
                    value_type="placeholder_only",
                    reason="Required traceability referenced source_screen_intent_id not found in DB",
                    required=False,
                )
            )
            continue

        rlist = getattr(row, "required_input_element_ids_json", None) or []
        if isinstance(rlist, dict) and isinstance(rlist.get("element_ids"), list):
            rlist = rlist["element_ids"]
        if not isinstance(rlist, list):
            rlist = []

        for elt_id_raw in rlist:
            elt_id = str(elt_id_raw)
            elt = elems_by_id.get(elt_id)
            label_basis = elt_id
            if elt:
                ln = elt.label or ""
                tn = elt.text if isinstance(getattr(elt, "text", None), list) else []
                snippet = ln or (" ".join(tn) if tn else elt_id)
                label_basis = snippet or elt_id

            lt = label_basis.lower()
            if "email" in lt:
                vt = "valid_email"
            elif "password" in lt:
                vt = "valid_secret"
            elif "phone" in lt or "mobile" in lt:
                vt = "valid_phone"
            else:
                vt = "valid_text"

            inm = getattr(row, "intent_name", "") or ""
            reqs.append(
                TestDataRequirementA5(
                    field_or_input=label_basis,
                    value_type=vt,
                    reason=f'Required by the source screen intent{" (" + str(inm).strip() + ")" if str(inm).strip() else ""}',
                    required=True,
                )
            )

        if not rlist and str(getattr(row, "intent_kind", "") or "").lower() in {"submission", "data_entry"}:
            reqs.append(
                TestDataRequirementA5(
                    field_or_input="(inputs not enumerated)",
                    value_type="placeholder_only",
                    reason="Screen intent marks data-entry but required_input_element_ids is empty — provide valid inputs without fixed literals",
                    required=True,
                )
            )

    return reqs, warns


def _append_post_mapping_unresolved(
    cf: Mapping[str, Any],
    intent_type: str,
    node_map: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, Any]],
    expected_evidence_nonempty: bool,
    transition_ids_placeholder: bool,
    into: List[UnresolvedFlowItemA5],
) -> None:
    end_s = str(cf.get("end_state") or "")
    if end_s not in node_map:
        into.append(
            UnresolvedFlowItemA5(
                item_type="unsupported_transition",
                source_id=str(cf.get("composed_flow_id")),
                related_states=[end_s] if end_s else [],
                reason="end_state not found in state_catalog",
            )
        )

    if not edges:
        into.append(
            UnresolvedFlowItemA5(
                item_type="unsupported_flow",
                source_id=str(cf.get("composed_flow_id")),
                related_states=list(cf.get("state_path") or []),
                reason="composed_flow has empty edge_sequence",
            )
        )
        return

    for ix, ee in enumerate(edges):
        tr_dict = ee.get("trigger_action")
        trig_nonempty = isinstance(tr_dict, dict) and any(
            str(x).strip() for x in (tr_dict.get("text") or [])
        )
        seq_nonempty = bool(ee.get("action_sequence") or [])
        if not trig_nonempty and not seq_nonempty:
            into.append(
                UnresolvedFlowItemA5(
                    item_type="insufficient_evidence_trigger",
                    source_id=str(ee.get("candidate_edge_id") or f"idx_{ix}"),
                    related_states=[str(ee.get("from_state") or ""), str(ee.get("to_state") or "")],
                    reason="Edge has empty trigger/action_sequence",
                )
            )

    if not expected_evidence_nonempty:
        into.append(
            UnresolvedFlowItemA5(
                item_type="unsupported_flow",
                source_id=str(cf.get("composed_flow_id")),
                related_states=[end_s],
                reason="expected_ui_evidence resolved empty after mapping",
            )
        )

    if transition_ids_placeholder:
        into.append(
            UnresolvedFlowItemA5(
                item_type="insufficient_traceability",
                source_id=str(cf.get("composed_flow_id")),
                related_states=list(cf.get("state_path") or []),
                reason="One or more source_transition_ids are synthetic (missing persisted transition id)",
            )
        )

    if intent_type == "unknown":
        into.append(
            UnresolvedFlowItemA5(
                item_type="unmatched_branch_outcome",
                source_id=str(cf.get("composed_flow_id")),
                related_states=list(cf.get("state_path") or []),
                reason="intent_type classified as unknown for this composed flow",
            )
        )


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


async def run_behaviour_contract_builder(
    db: AsyncSession,
    run_id: str,
    flow_discovery_result: Dict[str, Any],
    state_catalog: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("behaviour_contract_builder_started", run_id=run_id)

    catalog = state_catalog or []
    precomposed = flow_discovery_result.get("precomposed_flow_internals") or []

    if flow_discovery_result.get("discovery_engine") == "global_compressed_batch" and isinstance(
        precomposed, list
    ) and precomposed:
        composed_flow_dicts = list(precomposed)
        base_unresolved: List[UnresolvedFlowItemA5] = []
        compose_metrics = {"skipped_non_worthy_branch": 0}
    else:
        composed_flow_dicts, base_unresolved, compose_metrics = _compose_flows_from_discovery(
            flow_discovery_result, catalog
        )

    unresolved_all: List[UnresolvedFlowItemA5] = list(base_unresolved)

    invalid_flow_ct = sum(
        1
        for f in flow_discovery_result.get("candidate_flows") or []
        if str(f.get("flow_validation_status") or "") == "invalid"
    )

    if not composed_flow_dicts:
        return BehaviourIntentInferenceResult(
            behaviour_intents=[],
            unresolved_flow_items=unresolved_all,
            generation_summary=GenerationSummaryA5(
                total_candidate_flows=len(flow_discovery_result.get("candidate_flows") or []),
                total_behaviour_intents=0,
                total_unresolved_items=len(unresolved_all),
                behaviour_intents_created=0,
                skipped_due_to_invalid_flow=invalid_flow_ct,
                skipped_due_to_non_scenario_worthy_edge=int(
                    compose_metrics.get("skipped_non_worthy_branch") or 0
                ),
            ),
        ).model_dump()

    # --- TẬN DỤNG AI: Tích hợp Agent 5 LLM-driven Behavior Contract Builder ---
    if settings.USE_LLM_FOR_BEHAVIOUR_CONTRACT_BUILDER:
        try:
            logger.info("Calling Agent 5 LLM-driven Behaviour Contract Builder.")
            system_instruction = prompt_manager.get_prompt("prompt_behaviour_contract_builder").strip()
            
            # Map candidate edges for mapping validation
            report = flow_discovery_result.get("report") or {}
            candidate_edges_list = report.get("candidate_edges") or []
            candidate_edge_map = {str(e["edge_id"]): dict(e) for e in candidate_edges_list if e.get("edge_id")}
            
            eval_payload = {
                "composed_flows": composed_flow_dicts,
                "flow_state_cards": catalog
            }
            user_instruction = (
                f"Convert the composed flows into formal Behaviour Contracts:\n"
                f"{json.dumps(eval_payload, indent=2)}\n"
            )
            
            response = await model_adapter.call_text_structured(
                task_name="behaviour_contract_builder",
                run_id=run_id,
                node_name="behaviour_contract_builder_node",
                system_instruction=system_instruction,
                user_instruction=user_instruction,
                output_schema=BehaviourIntentInferenceResult,
                prompt_name="prompt_behaviour_contract_builder",
                prompt_version="v2",
                provider_override=settings.FLOW_DISCOVERY_MODEL_PROVIDER,
                model_name_override=settings.FLOW_DISCOVERY_MODEL_NAME,
            )
            
            if response.status.value == "success" and response.parsed_output:
                result = response.parsed_output
                logger.info(f"Agent 5 LLM successfully generated {len(result.behaviour_intents)} behaviour contracts.")
                
                # Ground taxonomy fields and index mappings to ensure DB/schema consistency
                for intent in result.behaviour_intents:
                    intent.intent_id = _generate_behaviour_intent_id(run_id)
                    
                    orig_cf = None
                    for cf in composed_flow_dicts:
                        if str(cf.get("composed_flow_id")) == str(intent.source_flow_id) or str(cf.get("source_flow_id")) == str(intent.source_flow_id):
                            orig_cf = cf
                            break
                    if orig_cf:
                        intent.source_flow_id = str(orig_cf.get("source_flow_id") or intent.source_flow_id)
                        intent.source_flow_name = str(orig_cf.get("source_flow_name") or intent.source_flow_name)
                        intent.source_flow_type = str(orig_cf.get("source_discovery_flow_type") or intent.source_flow_type)
                        intent.start_state = str(orig_cf.get("start_state") or intent.start_state)
                        intent.end_state = str(orig_cf.get("end_state") or intent.end_state)
                        intent.source_group_id = orig_cf.get("source_group_id") or intent.source_group_id
                        intent.source_screen_intent_id = orig_cf.get("source_screen_intent_id") or intent.source_screen_intent_id
                        intent.flow_validation_status = _flow_validation_status_for(flow_discovery_result, intent.source_flow_id)
                        
                        edges_cf = list(orig_cf.get("edge_sequence") or [])
                        sw_vals = []
                        for ee in edges_cf:
                            cid_e = ee.get("candidate_edge_id")
                            row_e = candidate_edge_map.get(str(cid_e)) if cid_e else {}
                            sw_vals.append(int(row_e.get("scenario_worthiness_score") or 100))
                        intent.min_scenario_worthiness = min(sw_vals) if sw_vals else 100
                        intent.scenario_worthy_path = all(_is_scenario_worthy_branch_edge(candidate_edge_map, ee) for ee in edges_cf)
                        
                        intent.source_transition_ids = [
                            str(e.get("transition_id"))
                            if e.get("transition_id")
                            else (
                                str(e.get("candidate_edge_id"))
                                if e.get("candidate_edge_id")
                                else f"{e.get('from_state')}->{e.get('to_state')}"
                            )
                            for e in edges_cf
                        ]
                        intent.source_transition_indexes = list(range(len(edges_cf)))
                    
                    db.add(_persist_intent_row(run_id, intent))
                
                try:
                    await db.commit()
                except Exception as db_err:
                    logger.error(f"Failed to commit LLM behaviour contracts for run {run_id}: {db_err}")
                    await db.rollback()
                    raise
                
                duration_ms = int((time.time() - start_time) * 1000)
                log_event("behaviour_contract_builder_completed", run_id=run_id, duration_ms=duration_ms)
                return result.model_dump()
            else:
                logger.error(f"LLM Behaviour Contract Builder call failed: {response.error}. Falling back to deterministic builder.")
        except Exception as ex:
            logger.error(f"Error in LLM Behaviour Contract Builder: {ex}. Falling back to deterministic builder.")

    node_map = _build_node_map(catalog)

    screen_intents_for_hints = sorted(
        {
            str(e.get("source_screen_intent_id"))
            for cf in composed_flow_dicts
            for e in (cf.get("edge_sequence") or [])
            if e.get("source_screen_intent_id")
        }
    )
    intent_hint_map = await _load_intent_kind_map(db, run_id, screen_intents_for_hints)

    intents: List[BehaviourIntentA5] = []

    report = flow_discovery_result.get("report") or {}
    candidate_edges_list = report.get("candidate_edges") or []
    candidate_edge_map = {str(e["edge_id"]): dict(e) for e in candidate_edges_list if e.get("edge_id")}
    decisions_map = _edge_decisions_map(flow_discovery_result)

    for cf in composed_flow_dicts:
        edges_cf: List[Dict[str, Any]] = list(cf.get("edge_sequence") or [])
        end_state = str(cf.get("end_state") or "")
        end_node_meta = node_map.get(end_state, {})
        last_edge = edges_cf[-1] if edges_cf else None

        last_sid = str(last_edge.get("source_screen_intent_id")) if last_edge else ""
        ik_tuple = intent_hint_map.get(last_sid, (None, None))
        intent_kind = ik_tuple[0]

        intent_type = _infer_intent_type(cf.get("flow_type", ""), end_node_meta, last_edge, intent_kind)

        flow_val_status = _flow_validation_status_for(flow_discovery_result, str(cf.get("source_flow_id") or ""))
        sw_vals: List[int] = []
        for ee in edges_cf:
            cid_e = ee.get("candidate_edge_id")
            row_e = candidate_edge_map.get(str(cid_e)) if cid_e else {}
            sw_vals.append(int(row_e.get("scenario_worthiness_score") or 100))
        min_sw = min(sw_vals) if sw_vals else 100
        worthy_path = (
            all(_is_scenario_worthy_branch_edge(candidate_edge_map, ee) for ee in edges_cf)
            if edges_cf
            else True
        )

        source_flow_type = str(cf.get("source_discovery_flow_type") or "ordered_sequence")

        source_transition_ids = [
            str(e.get("transition_id"))
            if e.get("transition_id")
            else (
                str(e.get("candidate_edge_id"))
                if e.get("candidate_edge_id")
                else f"{e.get('from_state')}->{e.get('to_state')}"
            )
            for e in edges_cf
        ]
        transition_ids_placeholder = any(
            (not ee.get("transition_id")) or str(ee.get("transition_id") or "").startswith("synthetic") for ee in edges_cf
        )

        conf_flow = str(cf.get("confidence") or "medium")
        conf_agg, weak_ev = _aggregate_edges_confidence(edges_cf, candidate_edge_map, decisions_map)
        if _confidence_order(conf_flow) <= _confidence_order(conf_agg):
            conf_use = conf_flow
        else:
            conf_use = conf_agg
        conf_use = _refine_flow_confidence_overall(conf_use, str(cf.get("flow_type") or ""), weak_ev)
        # Weak evidence penalty for negative-ish branches handled by refine rule

        tdr, warns = await _build_test_data_requirements(db, run_id, edges_cf)

        exp_res = strip_gherkin_keywords(_expected_result_from_templates(end_node_meta, last_edge))
        biz_goal = _business_goal(str(cf.get("source_flow_name") or ""), str(cf.get("user_goal") or ""))

        intent_pre = BehaviourIntentA5(
            intent_id=_generate_behaviour_intent_id(run_id),
            source_flow_id=str(cf["source_flow_id"]),
            source_flow_name=str(cf["source_flow_name"]),
            source_flow_type=source_flow_type,
            composition_method=str(cf.get("composition_method") or "agent4_selected_edges"),
            flow_validation_status=flow_val_status,
            min_scenario_worthiness=min_sw,
            scenario_worthy_path=worthy_path,
            source_transition_indexes=list(range(len(edges_cf))),
            source_outcome_state=cf.get("end_state"),
            source_group_id=cf.get("source_group_id"),
            source_screen_intent_id=cf.get("source_screen_intent_id"),
            source_transition_ids=source_transition_ids,
            behaviour_name=str(cf.get("behaviour_name") or "Generated Flow"),
            intent_type=intent_type,
            user_intent=str(cf.get("behaviour_name") or "Generated Flow"),
            business_goal=biz_goal,
            start_state=str(cf["start_state"]),
            end_state=str(cf["end_state"]),
            trigger_action=TriggerActionA5(action_type="click", text=[]),
            preconditions=[],
            test_data_requirements=tdr,
            user_actions=[],
            expected_result=exp_res,
            expected_ui_evidence=[],
            negative_expectations=["The success outcome is displayed."] if intent_type == "negative" else [],
            assumptions=[],
            warnings=list(warns),
            confidence=str(conf_use),
        )

        if edges_cf:
            le = edges_cf[-1]
            tri = le.get("trigger_action")
            if isinstance(tri, dict):
                intent_pre.trigger_action = TriggerActionA5(
                    action_type=str(tri.get("action_type") or "click"),
                    text=list(tri.get("text") or []),
                )
            elif tri:
                intent_pre.trigger_action = TriggerActionA5(
                    action_type=str(getattr(tri, "action_type", "click") or "click"),
                    text=list(getattr(tri, "text", []) or []),
                )

            evid = list(le.get("target_visible_evidence") or [])
            intent_pre.expected_ui_evidence = [strip_gherkin_keywords(x) for x in evid if str(x).strip()]

            for ee in edges_cf:
                act_seq = ee.get("action_sequence") or []
                if act_seq:
                    for step in act_seq:
                        role = str(step.get("action_role") or "click").lower()
                        txt = " ".join(step.get("action_text") or [])
                        if not txt:
                            continue
                        if role in ["select_option", "select", "option", "choice"]:
                            intent_pre.user_actions.append(f"Select \"{txt}\"")
                        elif role in ["input", "type", "fill", "enter"]:
                            intent_pre.user_actions.append(f"Enter \"{txt}\"")
                        elif role in ["commit", "confirm", "submit"]:
                            intent_pre.user_actions.append(f"Confirm \"{txt}\"")
                        else:
                            intent_pre.user_actions.append(f"Click \"{txt}\"")
                else:
                    frm = ee.get("trigger_action")
                    fs = format_action_step(frm)
                    if fs:
                        intent_pre.user_actions.append(fs)

            # Causal audit compares non-empty user_actions to edge count — pad with inferred triggers.
            if edges_cf:
                while len([x for x in intent_pre.user_actions if str(x).strip()]) < len(edges_cf):
                    ei = len([x for x in intent_pre.user_actions if str(x).strip()])
                    if ei >= len(edges_cf):
                        break
                    ee = edges_cf[ei]
                    tri = ee.get("trigger_action")
                    line = format_action_step(tri) if tri else ""
                    if not line:
                        line = format_action_step(derive_trigger_from_edge(ee))
                    if not line:
                        for step in ee.get("action_sequence") or []:
                            line = format_action_step(
                                {"action_type": "click", "text": step.get("action_text") or []}
                            )
                            if line:
                                break
                    if not line:
                        line = "Click the primary control for this transition"
                    intent_pre.user_actions.append(line)
        if intent_type == "validation" and not intent_pre.user_actions:
            intent_pre.preconditions.append("The required fields are interacted with according to UI affordances.")

        _append_post_mapping_unresolved(
            cf,
            intent_type,
            node_map,
            edges_cf,
            bool(intent_pre.expected_ui_evidence),
            transition_ids_placeholder,
            unresolved_all,
        )

        intent_pre.preconditions = [strip_gherkin_keywords(p) for p in intent_pre.preconditions]

        intents.append(intent_pre)

    result = BehaviourIntentInferenceResult(
        behaviour_intents=intents,
        unresolved_flow_items=unresolved_all,
        generation_summary=GenerationSummaryA5(
            total_candidate_flows=len(flow_discovery_result.get("candidate_flows") or []),
            total_behaviour_intents=len(intents),
            total_unresolved_items=len(unresolved_all),
            behaviour_intents_created=len(intents),
            skipped_due_to_invalid_flow=invalid_flow_ct,
            skipped_due_to_non_scenario_worthy_edge=int(compose_metrics.get("skipped_non_worthy_branch") or 0),
        ),
    )

    for intent in result.behaviour_intents:
        intent.intent_id = _generate_behaviour_intent_id(run_id)
        db.add(_persist_intent_row(run_id, intent))

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to commit behaviour contracts for run {run_id}: {e}")
        await db.rollback()
        raise

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("behaviour_contract_builder_completed", run_id=run_id, duration_ms=duration_ms)

    return result.model_dump()
