"""
Intent-Aware Flow Discovery Service — Agent 4 (was Agent 3).
Discovers user behavior flows using Intent-aware Flow Context Data.
"""
import json
import time
import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.flow import Flow
from app.db.models.flow_transition import FlowTransition
from app.model_providers import model_adapter
from app.model_providers.schemas import UIFlowDiscoveryResult
from app.core.prompt_manager import prompt_manager
from app.services.candidate_edge_resolver_service import resolve_candidate_edges
from app.services.intent_aware_flow_discovery_hydrate import (
    build_flow_discovery_decision_report,
    compute_flow_confidence,
    derive_trigger_from_edge,
    evidence_level_for_edge_id,
    hypothesized_action_from_trigger,
    normalize_ordering_strength,
    reason_code_for_edge_id,
)
from app.services.intent_aware_flow_discovery_validate import validate_and_repair_flow_discovery


def _generate_flow_id(run_id: str) -> str:
    return f"flow_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


def _generate_transition_id(run_id: str) -> str:
    return f"tr_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


async def run_intent_aware_flow_discovery(
    db: AsyncSession,
    run_id: str,
    flow_context_package: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Groups canonical states into behavior flows using candidate_edge_id composition only.
    """
    start_time = time.time()
    log_event("intent_aware_flow_discovery_started", run_id=run_id)

    flow_state_cards = flow_context_package.get("flow_state_cards", [])
    if not flow_state_cards:
        empty = UIFlowDiscoveryResult(
            flow_discovery_result_id=f"fdr_{run_id[-6:]}_{uuid.uuid4().hex[:8]}",
            source_canonical_state_set_id=flow_context_package.get("flow_context_package_id", "unknown_set"),
            candidate_flows=[],
            semantic_clusters=[],
            uncertain_relations=[],
            discovery_warnings=["NO_FLOW_STATE_CARDS"],
        ).model_dump()
        empty["report"] = {
            "candidate_edge_count": 0,
            "candidate_flow_count": 0,
            "semantic_cluster_count": 0,
            "uncertain_relation_count": 0,
            "warnings": ["NO_FLOW_STATE_CARDS"],
            "candidate_edges": [],
            "validation_failed": False,
        }
        return empty

    candidate_edges = resolve_candidate_edges(run_id, flow_state_cards)
    candidate_edge_map: Dict[str, Dict[str, Any]] = {
        e["edge_id"]: e for e in candidate_edges if e.get("edge_id")
    }

    if not candidate_edges:
        empty = UIFlowDiscoveryResult(
            flow_discovery_result_id=f"fdr_{run_id[-6:]}_{uuid.uuid4().hex[:8]}",
            source_canonical_state_set_id=flow_context_package.get("flow_context_package_id", "unknown_set"),
            candidate_flows=[],
            semantic_clusters=[],
            uncertain_relations=[],
            discovery_warnings=["NO_CANDIDATE_EDGES"],
        ).model_dump()
        empty["report"] = {
            "candidate_edge_count": 0,
            "candidate_flow_count": 0,
            "semantic_cluster_count": 0,
            "uncertain_relation_count": 0,
            "warnings": ["NO_CANDIDATE_EDGES"],
            "flow_discovery_decision_report": {
                "accepted_edges": [],
                "rejected_edges": [],
                "local_interactions": [],
                "uncertain_edges": [],
            },
            "candidate_edges": [],
            "validation_failed": False,
        }
        return empty

    state_card_by_id: Dict[str, Dict[str, Any]] = {
        s["state_id"]: s for s in flow_state_cards if s.get("state_id")
    }

    system_instruction = prompt_manager.get_prompt("prompt_intent_aware_flow_discovery")

    eval_payload = {
        "flow_state_cards": flow_state_cards,
        "candidate_edges": candidate_edges,
    }

    user_instruction = (
        f"Evaluate the {len(candidate_edges)} candidate edges and compose them into behaviour flows:\n"
        f"{json.dumps(eval_payload, indent=2)}\n"
    )

    response = await model_adapter.call_text_structured(
        task_name="intent_aware_flow_discovery",
        run_id=run_id,
        node_name="intent_aware_flow_discovery_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=UIFlowDiscoveryResult,
        prompt_name="prompt_intent_aware_flow_discovery",
        prompt_version="v2",
        provider_override=settings.FLOW_DISCOVERY_MODEL_PROVIDER,
        model_name_override=settings.FLOW_DISCOVERY_MODEL_NAME,
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Intent-Aware Flow Discovery failed: {response.error}")
        err = UIFlowDiscoveryResult(
            flow_discovery_result_id=f"fdr_{run_id[-6:]}_{uuid.uuid4().hex[:8]}",
            source_canonical_state_set_id=flow_context_package.get("flow_context_package_id", "unknown_set"),
            candidate_flows=[],
            semantic_clusters=[],
            uncertain_relations=[],
            discovery_warnings=[str(response.error or "LLM_FAILED")],
        ).model_dump()
        err["report"] = {
            "error": str(response.error),
            "candidate_edge_count": len(candidate_edges),
            "candidate_flow_count": 0,
            "candidate_edges": candidate_edges,
            "validation_failed": True,
        }
        return err

    parsed: UIFlowDiscoveryResult = response.parsed_output
    result, val_meta = validate_and_repair_flow_discovery(parsed, candidate_edge_map, state_card_by_id)

    flow_id_map: Dict[str, str] = {}
    transition_id_map: Dict[str, str] = {}

    edge_decisions_list = list(result.edge_decisions)

    for flow_data in result.candidate_flows:
        db_flow_id = _generate_flow_id(run_id)
        flow_id_map[flow_data.flow_id] = db_flow_id

        conf_float, conf_label = compute_flow_confidence(
            list(flow_data.transition_edge_ids),
            list(flow_data.alternative_outcome_edge_ids),
            candidate_edge_map,
        )

        flow_row = Flow(
            id=db_flow_id,
            run_id=run_id,
            name=flow_data.flow_name,
            flow_type=flow_data.flow_type,
            flow_label=flow_data.flow_name,
            input_level="AGENT_4_INTENT_AWARE_FLOW_DISCOVERY",
            entry_state_id=flow_data.ordered_states[0] if flow_data.ordered_states else None,
            ordered_state_ids_json={"ids": flow_data.ordered_states},
            user_goal=flow_data.user_goal,
            confidence=conf_float,
            confidence_label=conf_label,
        )
        db.add(flow_row)

        for eid in flow_data.transition_edge_ids:
            edge = candidate_edge_map.get(eid)
            if not edge:
                continue
            db_tr_id = _generate_transition_id(run_id)
            transition_id_map[f"{flow_data.flow_id}:{eid}"] = db_tr_id
            trig = derive_trigger_from_edge(edge)
            seq = edge.get("action_sequence") or []
            step0 = seq[0] if seq else {}
            rc = reason_code_for_edge_id(eid, edge_decisions_list) or "hydrated_from_candidate_edge"
            ev_lvl = evidence_level_for_edge_id(eid, edge_decisions_list)

            cp = edge.get("context_parameters") or []
            cp_json = [c if isinstance(c, dict) else {} for c in cp]

            tr_row = FlowTransition(
                id=db_tr_id,
                run_id=run_id,
                flow_id=db_flow_id,
                from_state_id=edge["from_state"],
                to_state_id=edge["to_state"],
                source_group_id=step0.get("source_group_id"),
                source_screen_intent_id=step0.get("source_screen_intent_id"),
                transition_type="direct_transition",
                trigger_json=trig,
                hypothesized_action=hypothesized_action_from_trigger(trig),
                ordering_strength=normalize_ordering_strength(ev_lvl),
                transition_basis=rc,
                supporting_evidence_refs_json={
                    "source": edge.get("source_visible_evidence") or [],
                    "target": edge.get("target_visible_evidence") or [],
                    "score_reasons": edge.get("edge_score_reasons") or [],
                },
                reason=rc,
                evidence_json={
                    "edge_score": edge.get("edge_score"),
                    "edge_risk_flags": edge.get("edge_risk_flags") or [],
                    "context_parameters": cp_json,
                },
            )
            db.add(tr_row)

        for eid in flow_data.alternative_outcome_edge_ids:
            edge = candidate_edge_map.get(eid)
            if not edge:
                continue
            db_tr_id = _generate_transition_id(run_id)
            transition_id_map[f"{flow_data.flow_id}:{eid}"] = db_tr_id
            trig = derive_trigger_from_edge(edge)
            seq = edge.get("action_sequence") or []
            step0 = seq[0] if seq else {}
            rc = reason_code_for_edge_id(eid, edge_decisions_list) or "hydrated_from_candidate_edge"
            ev_lvl = evidence_level_for_edge_id(eid, edge_decisions_list)
            cp = edge.get("context_parameters") or []
            cp_json = [c if isinstance(c, dict) else {} for c in cp]

            tr_row = FlowTransition(
                id=db_tr_id,
                run_id=run_id,
                flow_id=db_flow_id,
                from_state_id=edge["from_state"],
                to_state_id=edge["to_state"],
                source_group_id=step0.get("source_group_id"),
                source_screen_intent_id=step0.get("source_screen_intent_id"),
                transition_type="alternative_outcome",
                trigger_json=trig,
                hypothesized_action=hypothesized_action_from_trigger(trig),
                ordering_strength=normalize_ordering_strength(ev_lvl),
                transition_basis=rc,
                supporting_evidence_refs_json={
                    "source": edge.get("source_visible_evidence") or [],
                    "target": edge.get("target_visible_evidence") or [],
                    "score_reasons": edge.get("edge_score_reasons") or [],
                },
                reason=rc,
                evidence_json={
                    "edge_score": edge.get("edge_score"),
                    "edge_risk_flags": edge.get("edge_risk_flags") or [],
                    "context_parameters": cp_json,
                },
            )
            db.add(tr_row)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    out = result.model_dump()

    decision_report = build_flow_discovery_decision_report(edge_decisions_list)

    for flow_dict in out.get("candidate_flows") or []:
        old_fid = flow_dict.get("flow_id")
        if old_fid in flow_id_map:
            edge_to_tid: Dict[str, str] = {}
            for eid in flow_dict.get("transition_edge_ids") or []:
                k = f"{old_fid}:{eid}"
                if k in transition_id_map:
                    edge_to_tid[eid] = transition_id_map[k]
            for eid in flow_dict.get("alternative_outcome_edge_ids") or []:
                k = f"{old_fid}:{eid}"
                if k in transition_id_map:
                    edge_to_tid[eid] = transition_id_map[k]
            flow_dict["transition_id_by_candidate_edge_id"] = edge_to_tid
            flow_dict["flow_id"] = flow_id_map[old_fid]

    report = {
        "candidate_flow_count": len(result.candidate_flows),
        "semantic_cluster_count": len(result.semantic_clusters),
        "uncertain_relation_count": len(result.uncertain_relations),
        "warnings": result.discovery_warnings,
        "candidate_edge_count": len(candidate_edges),
        "candidate_edges": candidate_edges,
        "flow_discovery_decision_report": decision_report,
        "validation_failed": bool(val_meta.get("validation_failed")),
        "flows_low_confidence": val_meta.get("flows_low_confidence") or [],
    }

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("intent_aware_flow_discovery_completed", run_id=run_id, duration_ms=duration_ms)

    out["report"] = report
    return out
