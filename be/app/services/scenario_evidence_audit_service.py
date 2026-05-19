"""
Scenario Evidence Audit Service — Agent 7.
Acts as a judge to audit generated scenarios against UI evidence and screen intents.
"""
from __future__ import annotations

import datetime
import json
import math
import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.behaviour_scenario import BehaviourScenario
from app.model_providers import model_adapter
from app.model_providers.schemas import (
    FinalOutputSummaryA7,
    ScenarioAcceptanceDecisionA7,
    ScenarioValidationResult,
    ValidatedScenarioA7,
)
from app.constants.validation_artifacts import SCENARIO_EVIDENCE_AUDIT_REPORT_ARTIFACT
from app.constants.edge_taxonomy import FATAL_EDGE_RISK_FLAGS, SCENARIO_WORTHY_BRANCH_ROLES
from app.services.json_report_artifact import save_json_report_artifact
from app.services.ui_text_normalize import normalize_ui_text

_SCENARIO_VALIDATION_ARTIFACT = SCENARIO_EVIDENCE_AUDIT_REPORT_ARTIFACT
_SCENARIO_VALIDATION_SUBPATH = "validation/scenario_evidence_audit_report.json"

_AUDIT_REPORT_FLAGS: Dict[str, Any] = {
    "auto_retry_enabled": False,
    "revision_suggestions_mode": "report_only",
}

_VALIDATION_STATUSES = frozenset({"validated", "low_confidence", "needs_revision", "rejected"})

_MONTH_DAY_PATTERN = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}(?:,\s*\d{4})?\b",
    re.I,
)


def build_audit_ui_evidence_package_from_compressed(
    state_catalog: List[Dict[str, Any]],
    compressed_pkg: Dict[str, Any],
) -> Dict[str, Any]:
    """Inflate compressed cards into pseudo extracted_states for grounding + LLM audit context."""

    cards_by_id = {str(c.get("state_id")): c for c in (compressed_pkg.get("compressed_catalog") or [])}

    extracted: List[Dict[str, Any]] = []
    for st in state_catalog:
        sid = str(st.get("state_id") or "")
        if not sid:
            continue
        cc = cards_by_id.get(sid) or {}

        ves: List[Dict[str, Any]] = []
        acts: List[Dict[str, Any]] = []
        fbs: List[Dict[str, Any]] = []

        if cc:
            sp = str(cc.get("screen_purpose") or "").strip()
            if sp:
                ves.append({"element_id": f"{sid}_purpose", "element_type": "heading", "text": [sp]})

            for el in cc.get("visible_elements") or []:
                if isinstance(el, dict) and el.get("text"):
                    ves.append(dict(el))

            for row in cc.get("visible_feedback") or []:
                if not isinstance(row, dict):
                    continue
                fid = row.get("feedback_id")
                if fid:
                    fbs.append(
                        {
                            "feedback_id": str(fid),
                            "feedback_type": str(row.get("feedback_type") or "info"),
                            "text": [str(t) for t in (row.get("text") or []) if str(t).strip()],
                        }
                    )

            for act in cc.get("available_actions") or []:
                if isinstance(act, dict) and act.get("action_id"):
                    acts.append(
                        {
                            "action_id": str(act.get("action_id")),
                            "action_type": str(act.get("action_type") or "click"),
                            "text": [str(t) for t in (act.get("text") or []) if str(t).strip()],
                        }
                    )

            for ig in cc.get("screen_intents") or []:
                if not isinstance(ig, dict):
                    continue
                gid = str(ig.get("source_group_id") or ig.get("group_id") or "grp")
                goal = str(ig.get("local_user_goal") or ig.get("user_intent") or "").strip()
                if goal:
                    ves.append({"element_id": f"{sid}_{gid}_goal", "element_type": "text", "text": [goal]})

                def _add_action(pa: Dict[str, Any] | None, suffix: str) -> None:
                    if not isinstance(pa, dict):
                        return
                    aid = str(pa.get("action_id") or "").strip()
                    texts = [str(t) for t in (pa.get("text") or []) if str(t).strip()]
                    if not texts and not aid:
                        return
                    acts.append(
                        {
                            "action_id": aid or f"{sid}_{gid}_{suffix}",
                            "action_type": str(pa.get("action_type") or "click"),
                            "text": texts,
                        }
                    )

                _add_action(ig.get("primary_action"), "pa")
                _add_action(ig.get("commit_action"), "ca")
                for j, sec in enumerate(ig.get("secondary_actions") or []):
                    if isinstance(sec, dict):
                        _add_action(sec, f"sa{j}")

                for i, pa in enumerate(ig.get("primary_actions") or []):
                    if pa and not isinstance(pa, dict):
                        acts.append({"action_id": f"{sid}_{gid}_pa{i}", "action_type": "click", "text": [str(pa)]})
                for i, fb in enumerate(ig.get("feedback_signals") or []):
                    if fb:
                        fbs.append(
                            {"feedback_id": f"{sid}_{gid}_fb{i}", "feedback_type": "info", "text": [str(fb)]}
                        )

        merged = dict(st)
        merged["visible_elements"] = [*ves, *(merged.get("visible_elements") or [])]
        merged["available_actions"] = [*acts, *(merged.get("available_actions") or [])]
        merged["visible_feedback"] = [*fbs, *(merged.get("visible_feedback") or [])]
        extracted.append(merged)

    return {"extracted_states": extracted}


def _aggregate_final_summary(validated: Sequence[ValidatedScenarioA7]) -> FinalOutputSummaryA7:
    """Recompute summary from merged batches (per-batch LLM summaries are not merged)."""

    def cnt(status: str) -> int:
        return sum(1 for v in validated if (v.validation_status or "").lower() == status)

    return FinalOutputSummaryA7(
        validated_count=cnt("validated"),
        rejected_count=cnt("rejected"),
        low_confidence_count=cnt("low_confidence"),
        needs_revision_count=cnt("needs_revision"),
        total_count=len(validated),
    )


async def _persist_scenario_validation_report(
    db: AsyncSession, run_id: str, payload: Dict[str, Any]
) -> None:
    """Queue JSON report artifact rows. Caller commits the transaction."""
    await save_json_report_artifact(
        db,
        run_id=run_id,
        artifact_type=_SCENARIO_VALIDATION_ARTIFACT,
        node_name="scenario_evidence_audit_node",
        storage_subpath=_SCENARIO_VALIDATION_SUBPATH,
        payload=payload,
    )


def revision_hints_from_validated_package(validated_pkg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten validated_scenarios[].revision_suggestions for pipeline reporting/UI only (no auto-regenerate)."""
    out: List[Dict[str, Any]] = []
    for vs in validated_pkg.get("validated_scenarios") or []:
        if not isinstance(vs, dict):
            continue
        sid = vs.get("scenario_id")
        for item in vs.get("revision_suggestions") or []:
            if isinstance(item, dict):
                hint = dict(item)
                hint.setdefault("scenario_id", sid)
                if hint.get("suggestion") or hint.get("issue_type") or hint.get("target"):
                    out.append(hint)
    return out


def _merge_audit_pipeline_report_into_payload(payload: Dict[str, Any]) -> None:
    """Attach standard audit/report flags without clobbering error keys."""
    base = payload.get("report")
    merged: Dict[str, Any] = dict(_AUDIT_REPORT_FLAGS)
    if isinstance(base, dict):
        merged.update(base)
    payload["report"] = merged


def _assertion_requires_ui_verbatim_pool_match(ass: Dict[str, Any]) -> bool:
    """Assertions that should count toward evidence_total/found vs end-state UI text pool."""
    a_type = (ass.get("assertion_type") or "").lower()
    if a_type in ("state_reached", "state_transition"):
        return False
    if ass.get("ui_text_grounding_required") is False:
        return False
    return True


def _collect_pool_lines(state_obj: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for group in ("visible_elements", "available_actions", "visible_feedback"):
        for item in state_obj.get(group, []) or []:
            for t in item.get("text", []) or []:
                lines.append(normalize_ui_text(str(t)))
    return lines


def _pool_matches_trigger(pool_lines: Sequence[str], triggers_norm: Sequence[str]) -> bool:
    if not triggers_norm:
        return False
    joined = normalize_ui_text(" ".join(pool_lines))
    for tr in triggers_norm:
        if not tr:
            continue
        if tr in joined:
            return True
        for line in pool_lines:
            if not line:
                continue
            if tr in line or line in tr:
                return True
    return False


def _transition_path_state_ids(
    scenario: Dict[str, Any], flow_discovery_result: Optional[Dict[str, Any]]
) -> List[str]:
    if not flow_discovery_result:
        return []
    fid = str(scenario.get("source_flow_id") or "")
    flows = flow_discovery_result.get("candidate_flows") or []
    cf: Optional[Dict[str, Any]] = None
    for f in flows:
        if str(f.get("flow_id") or "") == fid:
            cf = f
            break
    if not cf:
        return []

    report = flow_discovery_result.get("report") or {}
    edges_map = {
        str(e["edge_id"]): e for e in (report.get("candidate_edges") or []) if e.get("edge_id")
    }
    edge_ids = [str(x) for x in (cf.get("transition_edge_ids") or [])]
    if not edge_ids:
        return []

    idxs = scenario.get("source_transition_indexes")
    edge_ids_use: List[str]
    if isinstance(idxs, list) and idxs:
        picked: List[str] = []
        for i in idxs:
            if isinstance(i, int) and 0 <= i < len(edge_ids):
                picked.append(edge_ids[i])
        edge_ids_use = picked if picked else edge_ids
    else:
        edge_ids_use = edge_ids

    ordered_states: List[str] = []
    seen: set[str] = set()
    for eid in edge_ids_use:
        edge = edges_map.get(str(eid))
        if not edge:
            continue
        for key in ("from_state", "to_state"):
            sid = edge.get(key)
            if sid is None:
                continue
            s = str(sid)
            if s not in seen:
                seen.add(s)
                ordered_states.append(s)
    return ordered_states


def _pre_audit_causal_chain(
    scenario: Dict[str, Any],
    flow_discovery_result: Optional[Dict[str, Any]],
    intent_package: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Structural causal checks independent from verbatim UI grounding."""
    causal_warnings: List[str] = []
    default_out = {
        "edge_ids_exist": True,
        "source_transition_chain_valid": True,
        "scenario_start_matches_first_edge": True,
        "scenario_end_matches_last_edge": True,
        "user_actions_match_edge_sequence": True,
        "edge_roles_scenario_worthy": True,
        "fatal_causal_violation": False,
        "causal_warnings": causal_warnings,
        "trigger_action_grounding_scope": str(
            (scenario.get("pre_audit_results") or {}).get("trigger_action_grounding_scope") or "none"
        ),
    }

    if not flow_discovery_result:
        return default_out

    fid = str(scenario.get("source_flow_id") or "")
    flows = flow_discovery_result.get("candidate_flows") or []
    cf: Optional[Dict[str, Any]] = None
    for f in flows:
        if str(f.get("flow_id") or "") == fid:
            cf = f
            break
    if not cf:
        causal_warnings.append("no_matching_candidate_flow")
        return default_out

    report = flow_discovery_result.get("report") or {}
    edges_map = {
        str(e["edge_id"]): e for e in (report.get("candidate_edges") or []) if e.get("edge_id")
    }

    edge_ids = [str(x) for x in (cf.get("transition_edge_ids") or [])]
    idxs = scenario.get("source_transition_indexes")
    edge_ids_use: List[str]
    if isinstance(idxs, list) and idxs:
        picked: List[str] = []
        for i in idxs:
            if isinstance(i, int) and 0 <= i < len(edge_ids):
                picked.append(edge_ids[i])
        edge_ids_use = picked if picked else edge_ids
    else:
        edge_ids_use = edge_ids

    edge_ids_exist = True
    if edge_ids_use:
        for eid in edge_ids_use:
            if eid not in edges_map:
                edge_ids_exist = False
                causal_warnings.append(f"missing_edge_id:{eid}")

    chain_valid = True
    prev_chain: List[str] = []
    for eid in edge_ids_use:
        edge = edges_map.get(eid)
        if not edge:
            chain_valid = False
            continue
        if not prev_chain:
            prev_chain.append(eid)
            continue
        prev_to = edges_map[prev_chain[-1]].get("to_state")
        cur_from = edge.get("from_state")
        if prev_to != cur_from:
            chain_valid = False
            causal_warnings.append(f"broken_chain:{eid}")
            break
        prev_chain.append(eid)

    start_ok = True
    end_ok = True
    if edge_ids_use:
        fe = edges_map.get(edge_ids_use[0])
        le = edges_map.get(edge_ids_use[-1])
        if fe:
            start_ok = str(scenario.get("start_state") or "") == str(fe.get("from_state") or "")
        if le:
            end_ok = str(scenario.get("end_state") or "") == str(le.get("to_state") or "")
        if not start_ok:
            causal_warnings.append("start_state_mismatch")
        if not end_ok:
            causal_warnings.append("end_state_mismatch")

    ua = scenario.get("user_actions") or []
    if isinstance(ua, list) and not [x for x in ua if str(x).strip()]:
        ua = []
    if edge_ids_use and not ua:
        ua = []
        for step in scenario.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if str(step.get("source") or "").lower() != "user_action":
                continue
            ua.append(str(step.get("text") or ""))

    actions_match = True
    if edge_ids_use and isinstance(ua, list):
        if len([x for x in ua if str(x).strip()]) < len(edge_ids_use):
            actions_match = False
            causal_warnings.append("user_actions_shorter_than_edge_sequence")

    roles_ok = True
    for eid in edge_ids_use:
        edge = edges_map.get(eid) or {}
        role = str(edge.get("scenario_branch_role") or "")
        if role and role not in SCENARIO_WORTHY_BRANCH_ROLES:
            roles_ok = False
            causal_warnings.append(f"non_worthy_role:{role}")
        if FATAL_EDGE_RISK_FLAGS.intersection(edge.get("edge_risk_flags") or []):
            roles_ok = False
            causal_warnings.append(f"fatal_risk_on_edge:{eid}")

    intent_hit: Dict[str, Any] = {}
    for bi in (intent_package or {}).get("behaviour_intents") or []:
        if str(bi.get("intent_id")) == str(scenario.get("source_intent_id") or ""):
            intent_hit = bi if isinstance(bi, dict) else {}
            break

    if settings.SCENARIO_GENERATION_PRODUCTION_GUARDS:
        if str(intent_hit.get("flow_validation_status") or "valid").lower() != "valid":
            chain_valid = False
            causal_warnings.append("intent_flow_invalid")

    fatal = False
    if not edge_ids_exist or not chain_valid or not start_ok or not end_ok:
        fatal = True

    return {
        "edge_ids_exist": edge_ids_exist,
        "source_transition_chain_valid": chain_valid,
        "scenario_start_matches_first_edge": start_ok,
        "scenario_end_matches_last_edge": end_ok,
        "user_actions_match_edge_sequence": actions_match,
        "edge_roles_scenario_worthy": roles_ok,
        "fatal_causal_violation": fatal,
        "causal_warnings": causal_warnings,
        "trigger_action_grounding_scope": str(
            (scenario.get("pre_audit_results") or {}).get("trigger_action_grounding_scope") or "none"
        ),
    }


def _apply_causal_hard_cap_on_validated(
    validated: List[ValidatedScenarioA7],
    causal_by_sid: Dict[str, Dict[str, Any]],
    scenarios_by_sid: Dict[str, Dict[str, Any]],
) -> List[ValidatedScenarioA7]:
    if not settings.SCENARIO_EVIDENCE_AUDIT_CAUSAL_HARD_CAP:
        return validated
    out: List[ValidatedScenarioA7] = []
    for v in validated:
        cr = causal_by_sid.get(str(v.scenario_id)) or {}
        pre = (scenarios_by_sid.get(str(v.scenario_id)) or {}).get("pre_audit_results") or {}
        trig_scope = str(pre.get("trigger_action_grounding_scope") or "none")
        nv = v
        st = (nv.validation_status or "").lower()
        if not cr.get("edge_ids_exist", True):
            nv = nv.model_copy(update={"validation_status": "rejected"})
        elif not cr.get("source_transition_chain_valid", True):
            nv = nv.model_copy(update={"validation_status": "rejected"})
        elif not cr.get("scenario_start_matches_first_edge", True) or not cr.get(
            "scenario_end_matches_last_edge", True
        ):
            nv = nv.model_copy(update={"validation_status": "rejected"})
        elif not cr.get("user_actions_match_edge_sequence", True):
            if st == "validated":
                nv = nv.model_copy(update={"validation_status": "needs_revision"})
        elif not cr.get("edge_roles_scenario_worthy", True):
            if st == "validated":
                nv = nv.model_copy(update={"validation_status": "low_confidence"})
        elif cr.get("fatal_causal_violation"):
            nv = nv.model_copy(update={"validation_status": "rejected"})
        elif trig_scope == "any_state" and st == "validated":
            chain_strong = bool(cr.get("source_transition_chain_valid")) and bool(cr.get("edge_ids_exist"))
            if not chain_strong:
                nv = nv.model_copy(update={"validation_status": "low_confidence"})
        out.append(nv)
    return out


def _extract_target_literals(assertions: Sequence[Dict[str, Any]]) -> List[str]:
    """Strict literals from assertion expected fields (times, currency, month-day, quantity word)."""
    grounding = [a for a in assertions if _assertion_requires_ui_verbatim_pool_match(a)]
    raw_corpus = " ".join(str(a.get("expected") or "") for a in grounding)
    if not raw_corpus.strip():
        return []

    seen: set[str] = set()
    out: List[str] = []

    def add_lit(fragment: str) -> None:
        n = normalize_ui_text(fragment)
        if n and n not in seen:
            seen.add(n)
            out.append(n)

    for m in re.findall(r"\b\d{1,2}[:\.]\d{2}\b", raw_corpus):
        add_lit(m.replace(".", ":"))

    for m in re.findall(r"\$\s*\d+(?:,\d{3})*(?:\.\d+)?", raw_corpus):
        add_lit(re.sub(r"\s+", "", m))

    for m in _MONTH_DAY_PATTERN.findall(raw_corpus):
        add_lit(m)

    if re.search(r"\bquantity\b", raw_corpus, flags=re.I):
        add_lit("quantity")

    return out


def _value_binding_corpus_normalized(scenario: Dict[str, Any]) -> str:
    parts: List[str] = []
    trig = scenario.get("trigger_action") or {}
    if isinstance(trig, dict):
        for t in trig.get("text") or []:
            parts.append(str(t))
    for step in scenario.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("source") or "").lower() != "user_action":
            continue
        parts.append(str(step.get("text") or ""))
    for td in scenario.get("test_data") or []:
        if not isinstance(td, dict):
            continue
        parts.append(str(td.get("value_placeholder") or ""))
        parts.append(str(td.get("data_name") or ""))
    return normalize_ui_text(" ".join(parts))


def _enforce_acceptance_and_reliability(
    validated: Sequence[ValidatedScenarioA7],
) -> Tuple[List[ValidatedScenarioA7], bool]:
    """Backend acceptance rule + reliability bands (post-LLM)."""
    reliability_downgrade_applied = False
    out: List[ValidatedScenarioA7] = []
    for v in validated:
        nv = v
        status = (nv.validation_status or "").lower()
        rel = float(nv.final_reliability if nv.final_reliability is not None else 0.0)

        if status == "validated" and rel < 0.70:
            reason = (nv.acceptance_decision.reason or "").strip()
            suffix = "[backend] final_reliability < 0.70 → low_confidence"
            nv = nv.model_copy(
                update={
                    "validation_status": "low_confidence",
                    "acceptance_decision": nv.acceptance_decision.model_copy(
                        update={"reason": f"{reason} {suffix}".strip()}
                    ),
                }
            )
            status = "low_confidence"
            reliability_downgrade_applied = True

        if status in ("validated", "low_confidence") and rel < 0.50:
            hf = nv.hallucination_flags.model_dump()
            any_hall = any(bool(val) for val in hf.values())
            new_status = "rejected" if any_hall else "needs_revision"
            nv = nv.model_copy(
                update={
                    "validation_status": new_status,
                    "acceptance_decision": ScenarioAcceptanceDecisionA7(
                        include_in_final_output=False,
                        reason=f"[backend] final_reliability < 0.50 → {new_status}",
                    ),
                }
            )
            status = new_status.lower()
            reliability_downgrade_applied = True

        if status in ("needs_revision", "rejected"):
            if nv.acceptance_decision.include_in_final_output:
                ar = nv.acceptance_decision.reason or ""
                nv = nv.model_copy(
                    update={
                        "acceptance_decision": nv.acceptance_decision.model_copy(
                            update={
                                "include_in_final_output": False,
                                "reason": f"{ar} [backend] excluded for status={status}".strip(),
                            }
                        )
                    }
                )

        out.append(nv)
    return out, reliability_downgrade_applied


def _batch_integrity_message(chunk: Sequence[Dict[str, Any]], batch_result: ScenarioValidationResult) -> Optional[str]:
    expected = {str(s.get("scenario_id")) for s in chunk}
    actual_list = [str(v.scenario_id) for v in batch_result.validated_scenarios]
    actual_set = set(actual_list)
    if len(actual_list) != len(actual_set):
        return "duplicate_scenario_ids_in_response"
    if expected != actual_set:
        missing = sorted(expected - actual_set)
        extra = sorted(actual_set - expected)
        return f"missing={missing} extra={extra}"
    return None


def _batch_semantics_message(batch_result: ScenarioValidationResult) -> Optional[str]:
    for v in batch_result.validated_scenarios:
        st = (v.validation_status or "").lower()
        if st not in _VALIDATION_STATUSES:
            return f"invalid_status:{v.scenario_id}:{v.validation_status}"
        if st in ("needs_revision", "rejected") and v.acceptance_decision.include_in_final_output:
            return f"invalid_include:{v.scenario_id}"
    return None


def _batch_response_issues(chunk: Sequence[Dict[str, Any]], batch_result: ScenarioValidationResult) -> Optional[str]:
    return _batch_integrity_message(chunk, batch_result) or _batch_semantics_message(batch_result)


def _pre_audit_grounding(
    test_scenarios: List[Dict[str, Any]],
    ui_state_package: Dict[str, Any],
    flow_discovery_result: Optional[Dict[str, Any]] = None,
    intent_package: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministically check if scenario text exists in UI evidence.
    Injects pre_audit_results into each scenario object.
    """
    states_map = {s["state_id"]: s for s in ui_state_package.get("extracted_states", [])}

    for scn in test_scenarios:
        grounding_report: Dict[str, Any] = {
            "trigger_action_found": False,
            "trigger_action_grounding_scope": "none",
            "trigger_action_found_in_source_state": False,
            "trigger_action_found_anywhere": False,
            "evidence_found_count": 0,
            "evidence_total_count": 0,
            "evidence_matches": [],
        }

        trigger_text_list = (scn.get("trigger_action") or {}).get("text", []) or []
        triggers_norm = [normalize_ui_text(str(t)) for t in trigger_text_list if str(t).strip()]

        found_source = False
        found_path = False
        found_any = False
        scope = "none"

        start_id = str(scn.get("start_state") or "")
        path_ids = _transition_path_state_ids(scn, flow_discovery_result)

        if triggers_norm:
            st_obj = states_map.get(start_id)
            if st_obj:
                pool = _collect_pool_lines(st_obj)
                found_source = _pool_matches_trigger(pool, triggers_norm)
            if found_source:
                scope = "source_state"
            else:
                for sid in path_ids:
                    st_obj_p = states_map.get(sid)
                    if not st_obj_p:
                        continue
                    pool_p = _collect_pool_lines(st_obj_p)
                    if _pool_matches_trigger(pool_p, triggers_norm):
                        found_path = True
                        scope = "transition_path"
                        break
                if not found_path:
                    for _st_id, st_any in states_map.items():
                        pool_a = _collect_pool_lines(st_any)
                        if _pool_matches_trigger(pool_a, triggers_norm):
                            found_any = True
                            scope = "any_state"
                            break

            grounding_report["trigger_action_found_in_source_state"] = found_source
            grounding_report["trigger_action_found_anywhere"] = found_source or found_path or found_any
            grounding_report["trigger_action_found"] = grounding_report["trigger_action_found_anywhere"]
            grounding_report["trigger_action_grounding_scope"] = scope if grounding_report["trigger_action_found"] else "none"

            assertions = scn.get("assertions", []) or []
            grounding_assertions = [a for a in assertions if _assertion_requires_ui_verbatim_pool_match(a)]
            target_literals = _extract_target_literals(grounding_assertions)

            if target_literals:
                binding = _value_binding_corpus_normalized(scn)
                missing_any = any(lit not in binding for lit in target_literals)
                if missing_any:
                    grounding_report["trigger_action_found"] = False
                    grounding_report["trigger_action_found_anywhere"] = False
                    grounding_report["trigger_action_found_in_source_state"] = False
                    grounding_report["trigger_action_grounding_scope"] = "none"

        end_state_id = scn.get("end_state")
        assertions = scn.get("assertions", []) or []
        pool_assertions = [a for a in assertions if _assertion_requires_ui_verbatim_pool_match(a)]
        if end_state_id in states_map and pool_assertions:
            st = states_map[end_state_id]
            target_pool = _collect_pool_lines(st)

            grounding_report["evidence_total_count"] = len(pool_assertions)
            for ass in pool_assertions:
                expected_norm = normalize_ui_text(str(ass.get("expected") or ""))
                match_found = False
                for pool_text in target_pool:
                    if not expected_norm:
                        continue
                    if expected_norm in pool_text or pool_text in expected_norm:
                        match_found = True
                        break
                if match_found:
                    grounding_report["evidence_found_count"] += 1
                    grounding_report["evidence_matches"].append(ass.get("expected"))

        kw = scn.get("pre_generation_grounding")
        if isinstance(kw, dict) and kw:
            grounding_report["keyword_anchor_grounding"] = {
                "keyword_anchor_coverage": kw.get("keyword_anchor_coverage"),
                "grounding_passed": kw.get("grounding_passed"),
                "required_anchor_count": kw.get("required_anchor_count"),
                "matched_anchor_count": kw.get("matched_anchor_count"),
                "missing_anchor_ids": kw.get("missing_anchor_ids") or [],
                "wrong_section_anchor_ids": kw.get("wrong_section_anchor_ids") or [],
                "unexpected_placeholders": kw.get("unexpected_placeholders") or [],
            }

        scn["pre_audit_results"] = grounding_report
        scn["pre_audit_causal_results"] = _pre_audit_causal_chain(
            scn, flow_discovery_result, intent_package
        )
    return test_scenarios


async def run_scenario_evidence_audit(
    db: AsyncSession,
    run_id: str,
    scenario_draft_package: Dict[str, Any],
    flow_discovery_result: Optional[Dict[str, Any]] = None,
    intent_package: Optional[Dict[str, Any]] = None,
    screen_intent_package: Optional[Dict[str, Any]] = None,
    *,
    state_catalog: Optional[List[Dict[str, Any]]] = None,
    compressed_catalog_package: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("scenario_evidence_audit_started", run_id=run_id)

    test_scenarios = scenario_draft_package.get("test_scenarios", [])
    if not test_scenarios:
        empty = ScenarioValidationResult(
            validated_scenarios=[],
            final_output_summary=FinalOutputSummaryA7(),
            package_warnings=["NO_SCENARIOS"],
        ).model_dump()
        _merge_audit_pipeline_report_into_payload(empty)
        await _persist_scenario_validation_report(db, run_id, empty)
        await db.commit()
        return empty

    ui_for_audit = {}
    if compressed_catalog_package and state_catalog:
        ui_for_audit = build_audit_ui_evidence_package_from_compressed(state_catalog, compressed_catalog_package)

    if ui_for_audit:
        test_scenarios = _pre_audit_grounding(
            test_scenarios, ui_for_audit, flow_discovery_result, intent_package
        )

    system_instruction = prompt_manager.get_prompt("prompt_scenario_evidence_audit")

    shared_context = {
        "behaviour_intents": intent_package.get("behaviour_intents", []) if intent_package else [],
        "candidate_flows": flow_discovery_result.get("candidate_flows", []) if flow_discovery_result else [],
        "screen_intent_package": screen_intent_package.get("screen_intent_catalog", []) if screen_intent_package else [],
        "ui_state_evidence": ui_for_audit.get("extracted_states", []) if ui_for_audit else [],
        "compressed_catalog": (compressed_catalog_package.get("compressed_catalog") if compressed_catalog_package else [])
        or [],
        "global_discovery": (flow_discovery_result or {}).get("global_discovery_result"),
    }

    batch_size = max(1, settings.SCENARIO_EVIDENCE_AUDIT_SCENARIO_BATCH_SIZE)
    total_batches = math.ceil(len(test_scenarios) / batch_size)

    validated_accum: List[ValidatedScenarioA7] = []
    warnings_accum: List[str] = []

    if total_batches > 1:
        logger.info(
            "scenario_evidence_audit batching: run=%s scenarios=%s batch_size=%s batches=%s",
            run_id,
            len(test_scenarios),
            batch_size,
            total_batches,
        )

    primary_model = settings.SCENARIO_VALIDATION_MODEL_NAME
    fallback_model = settings.SCENARIO_VALIDATION_FALLBACK_MODEL_NAME or primary_model

    for batch_idx, start in enumerate(range(0, len(test_scenarios), batch_size)):
        chunk = test_scenarios[start : start + batch_size]
        validation_input = {**shared_context, "test_scenarios": chunk}

        batch_header = ""
        if total_batches > 1:
            batch_header = (
                f"This is BATCH {batch_idx + 1} of {total_batches}. "
                "Audit ONLY the test_scenarios in this batch. "
                "Return validated_scenarios with exactly one entry per scenario in this batch "
                "(matching scenario_id).\n\n"
            )

        user_instruction = batch_header + (
            "Audit the following scenario draft package against the UI evidence and pipeline context.\n"
            "NOTE: Each scenario contains a 'pre_audit_results' field calculated by the backend. "
            "evidence_total_count/evidence_found_count exclude technical assertions (e.g. state_transition "
            "and ui_text_grounding_required=false), not verbatim UI snippets. "
            "If 'trigger_action_found' is true or evidence_found_count matches evidence_total_count, "
            "this indicates strong verbatim grounding for the counted assertions. Trust these results.\n"
            f"{json.dumps(validation_input, indent=2)}"
        )

        async def _call_llm(model_override: str):
            return await model_adapter.call_text_structured(
                task_name="scenario_evidence_audit",
                run_id=run_id,
                node_name="scenario_evidence_audit_node",
                system_instruction=system_instruction,
                user_instruction=user_instruction,
                output_schema=ScenarioValidationResult,
                prompt_name="prompt_scenario_evidence_audit",
                prompt_version="v1",
                provider_override=settings.SCENARIO_VALIDATION_MODEL_PROVIDER,
                model_name_override=model_override,
            )

        response = await _call_llm(primary_model)

        if response.status.value != "success" or not response.parsed_output:
            logger.error(
                "Scenario Evidence Audit failed (batch %s/%s): %s",
                batch_idx + 1,
                total_batches,
                response.error,
            )
            warnings_accum.append(f"BATCH_{batch_idx+1}_FAILED: {response.error}")
            for scn in chunk:
                validated_accum.append(ValidatedScenarioA7(
                    scenario_id=str(scn.get("scenario_id")),
                    validation_status="rejected",
                    final_reliability=0.0,
                    scores=ScoresA7(grounding=0, accuracy=0, readability=0),
                    acceptance_decision=ScenarioAcceptanceDecisionA7(
                        include_in_final_output=False,
                        reason=f"Batch {batch_idx+1} LLM audit failed"
                    ),
                ))
            continue

        batch_result: ScenarioValidationResult = response.parsed_output
        issue = _batch_response_issues(chunk, batch_result)

        if issue and fallback_model != primary_model:
            logger.warning(
                "scenario_evidence_audit batch %s/%s post-parse issue (%s); retrying fallback model",
                batch_idx + 1,
                total_batches,
                issue,
            )
            fb_resp = await _call_llm(fallback_model)
            if fb_resp.status.value == "success" and fb_resp.parsed_output:
                batch_result = fb_resp.parsed_output
                issue = _batch_response_issues(chunk, batch_result)

        if issue:
            logger.error(
                "Scenario Evidence Audit controlled failure (batch %s/%s): %s",
                batch_idx + 1,
                total_batches,
                issue,
            )
            warnings_accum.append(f"BATCH_{batch_idx+1}_FAILED: INTEGRITY_OR_SEMANTICS: {issue}")
            for scn in chunk:
                validated_accum.append(ValidatedScenarioA7(
                    scenario_id=str(scn.get("scenario_id")),
                    validation_status="rejected",
                    final_reliability=0.0,
                    scores=ScoresA7(grounding=0, accuracy=0, readability=0),
                    acceptance_decision=ScenarioAcceptanceDecisionA7(
                        include_in_final_output=False,
                        reason=f"Batch {batch_idx+1} integrity failed: {issue}"
                    ),
                ))
            continue

        validated_accum.extend(batch_result.validated_scenarios)
        warnings_accum.extend(batch_result.package_warnings)

    causal_by_sid = {
        str(s.get("scenario_id")): dict(s.get("pre_audit_causal_results") or {}) for s in test_scenarios
    }
    scenarios_by_sid = {str(s.get("scenario_id")): s for s in test_scenarios}

    enforced, reliability_downgrade_applied = _enforce_acceptance_and_reliability(validated_accum)
    enforced = _apply_causal_hard_cap_on_validated(enforced, causal_by_sid, scenarios_by_sid)

    result = ScenarioValidationResult(
        validated_scenarios=enforced,
        final_output_summary=_aggregate_final_summary(enforced),
        package_warnings=warnings_accum,
    )

    for vscn in result.validated_scenarios:
        result_db = await db.execute(
            select(BehaviourScenario).where(
                BehaviourScenario.id == vscn.scenario_id,
                BehaviourScenario.run_id == run_id,
            )
        )
        bs = result_db.scalar_one_or_none()
        if bs:
            bs.validation_status = vscn.validation_status
            bs.grounding_score = vscn.scores.flow_grounding_score
            bs.evidence_coverage_score = vscn.scores.evidence_grounding_score
            bs.final_reliability = vscn.final_reliability
            bs.scores_json = vscn.scores.model_dump()
            bs.step_audits_json = {"audits": [a.model_dump() for a in vscn.step_audits]}
            bs.hallucination_flags_json = vscn.hallucination_flags.model_dump()
            bs.revision_suggestions_json = {
                "items": [r.model_dump() for r in vscn.revision_suggestions]
            }
            bs.acceptance_decision_json = vscn.acceptance_decision.model_dump()
            bs.validated_at = datetime.datetime.utcnow()

    dumped = result.model_dump()
    _merge_audit_pipeline_report_into_payload(dumped)
    if reliability_downgrade_applied:
        dumped["report"]["reliability_downgrade_applied"] = True
    dumped["report"]["audit_pipeline_metrics"] = {
        "fatal_causal_violation_count": sum(
            1 for s in test_scenarios if (s.get("pre_audit_causal_results") or {}).get("fatal_causal_violation")
        ),
        "any_state_trigger_only_count": sum(
            1
            for s in test_scenarios
            if (s.get("pre_audit_results") or {}).get("trigger_action_grounding_scope") == "any_state"
        ),
        "scenario_excluded_by_backend_guardrail": sum(
            1 for v in enforced if (v.validation_status or "").lower() == "rejected"
        ),
    }
    await _persist_scenario_validation_report(db, run_id, dumped)
    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("scenario_evidence_audit_completed", run_id=run_id, duration_ms=duration_ms)

    return dumped
