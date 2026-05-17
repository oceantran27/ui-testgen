"""Unit tests for intent-aware flow discovery (edge-ID contract): hydrate + validate + composer wiring."""

from __future__ import annotations

from typing import Any, Dict

from app.model_providers.schemas import FlowDiscoveryA3, UIFlowDiscoveryResult
from app.services.behaviour_contract_service import _compose_flows_from_discovery
from app.services.intent_aware_flow_discovery_hydrate import (
    compute_flow_confidence,
    derive_trigger_from_edge,
    hydrate_flow_edges_for_compose,
)
from app.services.intent_aware_flow_discovery_validate import validate_and_repair_flow_discovery


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


def test_compute_flow_confidence_band_high():
    m = {"e1": _edge("e1", "st_a", "st_b", score=88)}
    conf, label = compute_flow_confidence(["e1"], [], m)
    assert conf == 0.9
    assert label == "high"


def test_validate_moves_negative_edge_off_main_transition():
    neg = _edge("neg", "st_a", "st_err", kind="validation_error", score=72)
    prog = _edge("ok", "st_a", "st_b", score=80)
    cmap = {"neg": neg, "ok": prog}
    cards = {
        "st_a": {"state_id": "st_a", "outcome_state_type": "neutral"},
        "st_b": {"state_id": "st_b", "outcome_state_type": "neutral"},
        "st_err": {"state_id": "st_err", "outcome_state_type": "validation_error"},
    }
    raw = UIFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryA3(
                flow_id="flow_test",
                flow_name="Test",
                flow_type="ordered_sequence",
                user_goal="move",
                ordered_states=["st_a", "st_err"],
                transition_edge_ids=["neg", "ok"],
                alternative_outcome_edge_ids=[],
            )
        ]
    )
    repaired, meta = validate_and_repair_flow_discovery(raw, cmap, cards)
    assert "neg" not in repaired.candidate_flows[0].transition_edge_ids
    assert "neg" in repaired.candidate_flows[0].alternative_outcome_edge_ids
    assert meta["validation_failed"] is False


def test_validate_strips_uncertain_edge_from_transition():
    ok = _edge("ok", "st_a", "st_b")
    cmap = {"ok": ok}
    cards = {
        "st_a": {"state_id": "st_a", "outcome_state_type": "neutral"},
        "st_b": {"state_id": "st_b", "outcome_state_type": "neutral"},
    }
    raw = UIFlowDiscoveryResult(
        edge_decisions=[],
        candidate_flows=[
            FlowDiscoveryA3(
                flow_id="flow_u",
                flow_name="U",
                flow_type="ordered_sequence",
                user_goal="x",
                ordered_states=["st_a", "st_b"],
                transition_edge_ids=["ok"],
                uncertain_edge_ids=["ok"],
            )
        ],
    )
    repaired, _meta = validate_and_repair_flow_discovery(raw, cmap, cards)
    assert repaired.candidate_flows[0].transition_edge_ids == []
    assert any("VALIDATION_UNCERTAIN_STRIPPED_FROM_TRANSITION" in w for w in repaired.discovery_warnings)


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
    composed, unresolved = _compose_flows_from_discovery(discovery, catalog)
    assert isinstance(composed, list)
    assert len(composed) >= 1


