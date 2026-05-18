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


def strip_gherkin_keywords(text: str) -> str:
    """Removes leading Given/When/Then/And keywords from a sentence."""
    if not text:
        return ""
    import re

    return re.sub(r"^(Given|When|Then|And|But)\s+", "", text.strip(), flags=re.I)


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


