"""Batched global flow discovery — structured text LLM call over trimmed behavioural state cards."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.flow import Flow
from app.db.models.flow_transition import FlowTransition
from app.model_providers import model_adapter
from app.model_providers.schemas import (
    ComposedFlowInternal,
    FlowDiscoveryCandidateFlow,
    FlowDiscoveryTriggerAction,
    GlobalFlowDiscoveryResult,
)
from app.services.global_flow_discovery_catalog import (
    build_llm_discovery_catalog,
    validate_discovery_input,
)
from app.services.global_flow_discovery_validate import validate_and_repair_global_flow_discovery
from app.services.flow_hydration_utils import (
    derive_trigger_from_edge,
    hypothesized_action_from_trigger,
    normalize_ordering_strength,
)


def _generate_global_flow_db_id(run_id: str) -> str:
    return f"flow_gfb_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


def _generate_global_transition_id(run_id: str) -> str:
    return f"tr_gfb_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


def _confidence_numeric(label: str) -> Tuple[float, str]:
    s = str(label or "").strip().lower()
    if "high" in s:
        return 0.88, "high"
    if "low" in s:
        return 0.35, "low"
    return 0.58, "medium"


def _internal_branch_type(last_outcome: str) -> str:
    ot = str(last_outcome or "").strip().lower()
    if ot in ("validation_error",):
        return "validation_branch"
    if ot in ("error", "warning", "failure"):
        return "error_branch"
    if ot in ("success",):
        return "main_success_path"
    return "navigation_branch"


def _card_by_state(compressed_pkg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(c.get("state_id") or ""): c for c in (compressed_pkg.get("compressed_catalog") or [])}


def _outcome_type_from_card(card: Dict[str, Any]) -> str:
    tax = card.get("taxonomy")
    if isinstance(tax, dict) and tax.get("outcome_state_type"):
        return str(tax.get("outcome_state_type") or "")
    return str(card.get("outcome_state_type") or "")


def _pick_screen_intent_for_state(card: Dict[str, Any]) -> Tuple[str, str]:
    for g in card.get("intent_groups") or []:
        iid = str(g.get("intent_id") or g.get("screen_intent_id") or "")
        gid = str(g.get("source_group_id") or g.get("group_id") or "") or "__whole_state__"
        if iid or gid:
            return iid, gid
    return "", ""


def _synthetic_candidate_edge_structured(
    *,
    frm: str,
    to_st: str,
    trig: Optional[FlowDiscoveryTriggerAction],
    sint: str,
    gid: str,
    edge_kind: str = "progress",
    scenario_branch_role: str = "core_progress",
) -> Dict[str, Any]:
    texts = list(trig.text) if trig else []
    seq_step: Dict[str, Any] = {
        "source_state": frm,
        "source_group_id": gid or None,
        "source_screen_intent_id": sint or None,
        "source_action_id": str(trig.action_id) if trig and str(trig.action_id).strip() else None,
        "action_role": "commit",
        "action_text": texts,
    }
    eid = f"gfb_ce_{frm}_{to_st}_{uuid.uuid4().hex[:10]}"
    row: Dict[str, Any] = {
        "edge_id": eid,
        "candidate_edge_id": eid,
        "from_state": frm,
        "to_state": to_st,
        "edge_kind": edge_kind,
        "scenario_role": "core",
        "scenario_branch_role": scenario_branch_role,
        "scenario_worthiness_score": 94 if edge_kind == "progress" else 82,
        "action_sequence": [seq_step],
        "alternative_action_sequences": [],
        "context_parameters": [],
        "source_visible_evidence": texts,
        "target_visible_evidence": [],
        "confidence": "high",
        "edge_score": 90.0 if edge_kind == "progress" else 72.0,
        "transition_id": eid.replace("ce_", "t_"),
        "trigger_action": {"action_type": (trig.action_type if trig else "") or "invoke_action", "text": texts},
        "source_group_id": gid,
        "source_screen_intent_id": sint,
    }
    return row


def compute_discovery_report(
    *,
    llm_catalog: Dict[str, Any],
    repaired: GlobalFlowDiscoveryResult,
    prompt_char_len: int,
    validation_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    input_states = len(llm_catalog.get("states") or [])
    accepted_steps = sum(len(f.ordered_steps) for f in repaired.candidate_flows)
    alt_ct = sum(len(f.alternative_outcomes) for f in repaired.candidate_flows)
    tok_est = max(1, prompt_char_len // 4)
    metrics = {
        "global_flow_discovery_input_state_count": input_states,
        "global_flow_discovery_input_token_estimate": tok_est,
        "semantic_cluster_count": len(repaired.semantic_clusters),
        "candidate_flow_count": len(repaired.candidate_flows),
        "accepted_ordered_step_count": accepted_steps,
        "alternative_outcome_count": alt_ct,
        "unassigned_state_count": len(repaired.unassigned_state_ids),
        "uncertain_relation_count": len(repaired.uncertain_relations),
        **validation_metrics,
    }
    return {
        "input_state_count": input_states,
        "candidate_flow_count": len(repaired.candidate_flows),
        "unassigned_state_count": len(repaired.unassigned_state_ids),
        "uncertain_relation_count": len(repaired.uncertain_relations),
        "global_discovery_input_catalog_char_len": prompt_char_len,
        "metrics": metrics,
    }


def assemble_flow_discovery_bundle(
    compressed_pkg: Dict[str, Any],
    repaired: GlobalFlowDiscoveryResult,
    *,
    discovery_report: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Produce a flow_discovery-shaped dict consumed by BehaviourContract + audit:
    synthetic candidate_edges, candidate_flows (edge-ref compatible), optional precomposed internals.
    """
    cards = _card_by_state(compressed_pkg)
    synthetic_edges_flat: List[Dict[str, Any]] = []

    cf_payload: List[Dict[str, Any]] = []
    precomposed: List[Dict[str, Any]] = []

    for flow in repaired.candidate_flows:
        fd = flow if isinstance(flow, FlowDiscoveryCandidateFlow) else FlowDiscoveryCandidateFlow.model_validate(flow)
        steps = list(fd.ordered_steps)
        ids_path = [s.state_id for s in steps]
        tx_ids: List[str] = []
        alt_ids: List[str] = []

        edge_seq_for_compose: List[Dict[str, Any]] = []

        for j in range(len(steps) - 1):
            frm = steps[j].state_id
            tb = steps[j + 1].state_id
            trig = steps[j].next_trigger_action

            frm_card = cards.get(frm, {})

            sint, gid = _pick_screen_intent_for_state(frm_card)

            edge = _synthetic_candidate_edge_structured(
                frm=frm,
                to_st=tb,
                trig=trig,
                sint=sint,
                gid=gid,
                edge_kind="progress",
                scenario_branch_role="core_progress",
            )
            synthetic_edges_flat.append(edge)

            cid = str(edge["candidate_edge_id"])
            tx_ids.append(cid)
            edge_seq_for_compose.append(edge)

        frm_card_root = cards.get(ids_path[0], {}) if ids_path else {}
        sint_root, gid_root = _pick_screen_intent_for_state(frm_card_root)

        for alt in fd.alternative_outcomes:
            fs = str(alt.from_state_id or "").strip()
            ts = str(alt.to_state_id or "").strip()
            fc = cards.get(fs, {})
            sint_a, gid_a = _pick_screen_intent_for_state(fc)
            sint_u, gid_u = (sint_a, gid_a) if (sint_a or gid_a) else (sint_root, gid_root)
            alt_edge = _synthetic_candidate_edge_structured(
                frm=fs,
                to_st=ts,
                trig=alt.trigger_action,
                sint=sint_u,
                gid=gid_u,
                edge_kind="alternative_outcome",
                scenario_branch_role="alternative_outcome",
            )
            synthetic_edges_flat.append(alt_edge)
            alt_ids.append(str(alt_edge["candidate_edge_id"]))

        last_sid = ids_path[-1] if ids_path else ""
        last_card = cards.get(last_sid, {})
        last_ft = _internal_branch_type(str(_outcome_type_from_card(last_card)))

        goal = (fd.user_goal or fd.flow_name or fd.rationale or "").strip()[:500]

        cf_row = {
            "flow_id": fd.flow_id,
            "flow_name": fd.flow_name,
            "flow_type": fd.flow_type,
            "user_goal": goal,
            "ordered_states": list(ids_path),
            "transition_edge_ids": tx_ids,
            "alternative_outcome_edge_ids": alt_ids,
            "local_interaction_edge_ids": [],
            "uncertain_edge_ids": [],
            "flow_validation_status": "valid",
            "confidence": str(fd.flow_confidence or "medium"),
        }
        cf_payload.append(cf_row)

        if len(ids_path) >= 1:
            precomposed.append(
                ComposedFlowInternal(
                    composed_flow_id=f"cf_gfb_{fd.flow_id}_{uuid.uuid4().hex[:8]}",
                    source_flow_id=fd.flow_id,
                    source_flow_name=fd.flow_name,
                    user_goal=str(cf_row["user_goal"]),
                    source_discovery_flow_type=fd.flow_type,
                    flow_type=last_ft,
                    start_state=str(ids_path[0]),
                    end_state=str(ids_path[-1]),
                    state_path=list(ids_path),
                    edge_sequence=edge_seq_for_compose,
                    source_trace=[],
                    composition_method="global_compressed_batch",
                    confidence=str(fd.flow_confidence or "medium"),
                    behaviour_name=str(fd.flow_name or cf_row["user_goal"]),
                    source_group_id=edge_seq_for_compose[-1].get("source_group_id") if edge_seq_for_compose else None,
                    source_screen_intent_id=(
                        edge_seq_for_compose[-1].get("source_screen_intent_id") if edge_seq_for_compose else None
                    ),
                ).model_dump()
            )

    report = {
        "candidate_edges": synthetic_edges_flat,
        "resolver_metrics": {"engine": "global_compressed_batch"},
        "pipeline_stop_after_discovery": False,
        **discovery_report,
    }

    sem_payload = [
        c.model_dump(mode="python") if hasattr(c, "model_dump") else c for c in repaired.semantic_clusters
    ]

    return {
        "discovery_engine": "global_compressed_batch",
        "global_discovery_result": repaired.model_dump(mode="python"),
        "candidate_flows": cf_payload,
        "semantic_clusters": sem_payload,
        "edge_decisions": [],
        "uncertain_relations": [
            ur.model_dump(mode="python") if hasattr(ur, "model_dump") else ur for ur in repaired.uncertain_relations
        ],
        "discovery_warnings": list(repaired.discovery_warnings),
        "report": report,
        "precomposed_flow_internals": precomposed,
    }


async def _persist_bridge_flow_rows(db: AsyncSession, run_id: str, bridge: Dict[str, Any]) -> None:
    """Persist Flow / FlowTransition rows mirroring compressed-global discovery."""

    compressed_stats = bridge.get("__compression_stats_snapshot__") or {}

    candidate_flow_rows = bridge.get("candidate_flows") or []
    rep = bridge.get("report") or {}
    cmap = rep.get("candidate_edges") or []
    cmap_by_edge = {str(e.get("candidate_edge_id") or e.get("edge_id")): e for e in cmap}

    for flow_row_ui in candidate_flow_rows:
        flow_ui_id = str(flow_row_ui.get("flow_id") or "")
        if not flow_ui_id:
            continue

        oid_path = list(flow_row_ui.get("ordered_states") or [])
        conf_val, conf_lbl = _confidence_numeric(flow_row_ui.get("confidence") or "medium")

        db_flow_id = _generate_global_flow_db_id(run_id)
        fw = Flow(
            id=db_flow_id,
            run_id=run_id,
            name=flow_row_ui.get("flow_name"),
            flow_type=str(flow_row_ui.get("flow_type") or "ordered_sequence"),
            flow_label=flow_row_ui.get("flow_name"),
            input_level="AGENT_GLOBAL_BATCH_COMPRESSED_FLOW_DISCOVERY",
            entry_state_id=oid_path[0] if oid_path else None,
            ordered_state_ids_json={"ids": oid_path},
            user_goal=str(flow_row_ui.get("user_goal") or ""),
            confidence=float(conf_val),
            confidence_label=str(conf_lbl),
        )
        db.add(fw)

        for e_ref in flow_row_ui.get("transition_edge_ids") or []:
            edge = cmap_by_edge.get(str(e_ref))
            if not edge:
                continue
            trig = derive_trigger_from_edge(edge)
            step0 = (edge.get("action_sequence") or [{}])[0] if edge.get("action_sequence") else {}

            db_tr_id = _generate_global_transition_id(run_id)
            tr_row = FlowTransition(
                id=db_tr_id,
                run_id=run_id,
                flow_id=db_flow_id,
                from_state_id=str(edge["from_state"]),
                to_state_id=str(edge["to_state"]),
                source_group_id=step0.get("source_group_id"),
                source_screen_intent_id=step0.get("source_screen_intent_id"),
                transition_type="direct_transition",
                trigger_json=trig,
                hypothesized_action=hypothesized_action_from_trigger(trig),
                ordering_strength=normalize_ordering_strength(str(edge.get("confidence") or "medium")),
                transition_basis="compressed_global_discovery",
                supporting_evidence_refs_json={"compression": compressed_stats},
                reason="compressed_global_discovery",
                evidence_json={"edge_kind": edge.get("edge_kind"), "synthetic_global": True},
            )
            db.add(tr_row)

    try:
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.error("persist global flow discovery failed run=%s: %s", run_id, exc)
        await db.rollback()


def _failure_bridge(run_id: str, *, warnings: List[str], failure_type: str) -> Dict[str, Any]:
    return {
        "discovery_engine": "global_compressed_batch",
        "global_discovery_result": GlobalFlowDiscoveryResult(discovery_warnings=list(warnings)).model_dump(mode="python"),
        "candidate_flows": [],
        "semantic_clusters": [],
        "edge_decisions": [],
        "uncertain_relations": [],
        "discovery_warnings": list(warnings),
        "report": {
            "candidate_edges": [],
            "pipeline_stop_after_discovery": True,
            "failure_type": failure_type,
            "metrics": {},
        },
        "precomposed_flow_internals": [],
    }


async def run_global_flow_discovery(
    db: AsyncSession,
    run_id: str,
    *,
    compressed_catalog_package: Dict[str, Any],
) -> Dict[str, Any]:
    t0 = time.time()

    llm_catalog = build_llm_discovery_catalog(compressed_catalog_package)
    ok_in, input_errs = validate_discovery_input(llm_catalog)
    if not ok_in:
        logger.error("global_flow_discovery invalid input run=%s: %s", run_id, input_errs)
        return _failure_bridge(run_id, warnings=input_errs, failure_type="GLOBAL_FLOW_DISCOVERY_INVALID_INPUT")

    body_json = json.dumps(llm_catalog, ensure_ascii=False)
    char_len = len(body_json)

    log_event(
        "global_flow_discovery_started",
        run_id=run_id,
        catalog_chars=char_len,
        screens=len(llm_catalog.get("states") or []),
    )

    system_instruction = prompt_manager.get_prompt("prompt_global_flow_discovery").strip()
    user_instruction = (
        "Compose behavioural flow candidates from the llm_discovery_catalog JSON below "
        "(states only — unordered set). Use state_id / action_id values verbatim from input.\n\n"
        f"{body_json}\n"
    )

    resp = await model_adapter.call_text_structured(
        task_name="global_flow_discovery",
        run_id=run_id,
        node_name="global_flow_discovery_service",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=GlobalFlowDiscoveryResult,
        prompt_name="prompt_global_flow_discovery",
        prompt_version="v2",
        provider_override=settings.FLOW_DISCOVERY_MODEL_PROVIDER,
        model_name_override=settings.FLOW_DISCOVERY_MODEL_NAME,
    )

    if getattr(resp.status, "value", str(resp.status)) != "success" or not resp.parsed_output:
        err = getattr(resp.error, "message", None) or str(resp.error or "LLM_FAILED")
        logger.error("global_flow_discovery failed run=%s: %s", run_id, err)
        bridge = _failure_bridge(run_id, warnings=[f"LLM_FAILED:{err}"], failure_type="GLOBAL_FLOW_DISCOVERY_LLM_FAILED")
        repl = bridge.get("report")
        if isinstance(repl, dict):
            repl["global_discovery_input_catalog_char_len"] = char_len
        return bridge

    repaired, val_metrics = validate_and_repair_global_flow_discovery(
        resp.parsed_output,
        llm_catalog=llm_catalog,
    )

    discovery_report = compute_discovery_report(
        llm_catalog=llm_catalog,
        repaired=repaired,
        prompt_char_len=char_len,
        validation_metrics=val_metrics,
    )

    bridge = assemble_flow_discovery_bundle(
        compressed_catalog_package,
        repaired,
        discovery_report=discovery_report,
    )
    bridge["__compression_stats_snapshot__"] = dict(compressed_catalog_package.get("compression_stats") or {})
    bridge["discovery_warnings"] = list(dict.fromkeys(bridge["discovery_warnings"]))

    repl = bridge.get("report")
    if isinstance(repl, dict):
        repl["global_discovery_input_catalog_char_len"] = char_len

    await _persist_bridge_flow_rows(db, run_id, bridge)

    dur_ms = int((time.time() - t0) * 1000)
    log_event(
        "global_flow_discovery_completed",
        run_id=run_id,
        flows=len(bridge.get("candidate_flows") or []),
        duration_ms=dur_ms,
    )

    return bridge
