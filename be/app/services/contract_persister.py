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


def _generate_behaviour_intent_id(run_id: str) -> str:
    """behaviour_intents.id is a global PK — never persist LLM ids directly."""
    return f"bi_{run_id[-6:]}_{uuid.uuid4().hex[:8]}"


async def _load_run_flow_rows(db: AsyncSession, run_id: str) -> List[Flow]:
    res = await db.execute(select(Flow).where(Flow.run_id == run_id))
    return list(res.scalars().all())


    by_pk = {str(f.id) for f in flows}
    if sem in by_pk:
        return sem
    for f in flows:
        pkg = f.flow_evidence_package_json or {}
        if str(pkg.get("discovery_source_flow_id") or "") == sem:
            return str(f.id)
    if source_flow_name:
        sn = source_flow_name.strip().lower()
        for f in flows:
            if (f.flow_label or "").strip().lower() == sn or (f.name or "").strip().lower() == sn:
                return str(f.id)
    return None


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
        raw_result_json=None,
    )


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


