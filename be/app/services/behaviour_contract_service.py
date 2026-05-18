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


from app.services.contract_persister import _generate_behaviour_intent_id, _load_run_flow_rows, _persist_intent_row, _load_intent_kind_map, _build_test_data_requirements
from app.services.flow_composer import _merge_candidate_edge_row, _is_scenario_worthy_branch_edge, _flow_validation_status_for, _build_node_map, _edge_decisions_map, _transition_dict_from_candidate, _normalize_edge_shapes, _apply_edge_roles, _chain_is_continuous, _flow_type_and_name_for_branch, _main_path_flow_type, _source_trace_steps, _build_main_composed_flow_for_discovery_flow, _all_classified_edges_union, _compose_flows_from_discovery
from app.services.intent_classifier import strip_gherkin_keywords, _score_text_match, _confidence_order, _aggregate_edges_confidence, _refine_flow_confidence_overall, _infer_intent_type, _expected_result_from_templates, _business_goal, _append_post_mapping_unresolved

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

    persisted_flows = await _load_run_flow_rows(db, run_id)

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

                llm_committed: List[BehaviourIntentA5] = []
                # Ground taxonomy fields and index mappings to ensure DB/schema consistency
                for intent in result.behaviour_intents:
                    intent.intent_id = _generate_behaviour_intent_id(run_id)

                    orig_cf = None
                    for cf in composed_flow_dicts:
                        if str(cf.get("composed_flow_id")) == str(intent.source_flow_id) or str(
                            cf.get("source_flow_id")
                        ) == str(intent.source_flow_id):
                            orig_cf = cf
                            break
                    if orig_cf:
                        intent.source_flow_id = str(orig_cf.get("source_flow_id") or intent.source_flow_id)
                        intent.source_flow_name = str(orig_cf.get("source_flow_name") or intent.source_flow_name)
                        intent.source_flow_type = str(
                            orig_cf.get("source_discovery_flow_type") or intent.source_flow_type
                        )
                        intent.start_state = str(orig_cf.get("start_state") or intent.start_state)
                        intent.end_state = str(orig_cf.get("end_state") or intent.end_state)
                        intent.source_group_id = orig_cf.get("source_group_id") or intent.source_group_id
                        intent.source_screen_intent_id = (
                            orig_cf.get("source_screen_intent_id") or intent.source_screen_intent_id
                        )
                        intent.flow_validation_status = _flow_validation_status_for(
                            flow_discovery_result, intent.source_flow_id
                        )

                        edges_cf = list(orig_cf.get("edge_sequence") or [])
                        sw_vals = []
                        for ee in edges_cf:
                            cid_e = ee.get("candidate_edge_id")
                            row_e = candidate_edge_map.get(str(cid_e)) if cid_e else {}
                            sw_vals.append(int(row_e.get("scenario_worthiness_score") or 100))
                        intent.min_scenario_worthiness = min(sw_vals) if sw_vals else 100
                        intent.scenario_worthy_path = all(
                            _is_scenario_worthy_branch_edge(candidate_edge_map, ee) for ee in edges_cf
                        )

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
                    llm_committed.append(intent)

                if llm_committed:
                    result.behaviour_intents = llm_committed
                    result.generation_summary.total_behaviour_intents = len(llm_committed)
                    result.generation_summary.behaviour_intents_created = len(llm_committed)
                    try:
                        await db.commit()
                    except Exception as db_err:
                        logger.error(f"Failed to commit LLM behaviour contracts for run {run_id}: {db_err}")
                        await db.rollback()
                        raise

                    duration_ms = int((time.time() - start_time) * 1000)
                    log_event("behaviour_contract_builder_completed", run_id=run_id, duration_ms=duration_ms)
                    return result.model_dump()

                logger.error(
                    "LLM behaviour contracts: none linked to persisted Flow rows. Pipeline cannot continue. run_id=%s",
                    run_id,
                )
                raise RuntimeError(f"Agent 5 LLM generated {len(result.behaviour_intents)} contracts but none linked to persisted flows.")
            else:
                logger.error(f"LLM Behaviour Contract Builder call failed: {response.error}.")
                raise RuntimeError(f"Agent 5 LLM call failed: {response.error}. Pipeline cannot continue without behaviour contracts.")
        except Exception as ex:
            logger.error(f"Error in LLM Behaviour Contract Builder: {ex}.")
            raise

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
            intent_id="__pending__",
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


