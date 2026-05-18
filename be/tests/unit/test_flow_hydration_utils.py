"""Unit tests for flow hydration utilities."""

from __future__ import annotations

import pytest
from typing import Any, Dict

from app.services.behaviour_contract_service import _compose_flows_from_discovery
from app.services.flow_hydration_utils import (
    derive_trigger_from_edge,
    hydrate_flow_edges_for_compose,
)


def _edge(
    eid: str,
    frm: str,
    to: str,
    *,
    kind: str = "progress",
    score: float = 88.0,
    risk_flags: list | None = None,
) -> Dict[str, Any]:
    return {
        "edge_id": eid,
        "from_state": frm,
        "to_state": to,
        "edge_kind": kind,
        "edge_score": score,
        "edge_risk_flags": risk_flags or [],
        "edge_score_reasons": [],
        "source_visible_evidence": ["src"],
        "target_visible_evidence": ["tgt"],
        "context_parameters": [],
        "action_sequence": [
            {
                "source_state": frm,
                "source_group_id": "g1",
                "source_screen_intent_id": "intent_1",
                "action_role": "commit",
                "action_text": ["Continue"],
            }
        ],
    }


def test_derive_trigger_from_edge_maps_commit_role():
    edge = _edge("e1", "st_a", "st_b")
    trig = derive_trigger_from_edge(edge)
    assert trig["action_type"] == "invoke_action"
    assert trig["text"] == ["Continue"]


def test_hydrate_flow_edges_for_compose_includes_transition_ids():
    ok = _edge("ok", "st_a", "st_b")
    flow = {
        "transition_edge_ids": ["ok"],
        "alternative_outcome_edge_ids": [],
    }
    trans, _alts = hydrate_flow_edges_for_compose(flow, {"ok": ok}, {"ok": "tr_db_1"})
    assert len(trans) == 1
    assert trans[0]["transition_id"] == "tr_db_1"
    assert trans[0]["candidate_edge_id"] == "ok"


def test_compose_flows_from_discovery_hydrates_from_report_candidate_edges():
    ok = _edge("ok", "st_a", "st_b")
    discovery = {
        "candidate_flows": [
            {
                "flow_id": "flow_db",
                "flow_name": "F",
                "transition_edge_ids": ["ok"],
                "alternative_outcome_edge_ids": [],
                "transition_id_by_candidate_edge_id": {"ok": "tr_1"},
            }
        ],
        "report": {"candidate_edges": [ok]},
    }
    catalog = [
        {
            "state_id": "st_a",
            "outcome_state_type": "neutral",
            "presentation_scope": "full_screen",
            "visible_feedback": [],
            "visible_elements": [],
        },
        {
            "state_id": "st_b",
            "outcome_state_type": "success",
            "presentation_scope": "full_screen",
            "visible_feedback": [],
            "visible_elements": [{"role_hint": "heading", "text": ["Done"]}],
        },
    ]
    composed, unresolved, _metrics = _compose_flows_from_discovery(discovery, catalog)
    assert isinstance(composed, list)
    assert len(composed) >= 1
