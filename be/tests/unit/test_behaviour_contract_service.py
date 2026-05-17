"""Unit tests for behaviour_contract_service (Agent 5)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services import behaviour_contract_service as bsvc
def _state(cid: str, oc: str = "neutral", pres: str = "full_screen") -> dict:
    return {
        "state_id": cid,
        "canonical_state_id": cid,
        "outcome_state_type": oc,
        "presentation_scope": pres,
        "visible_feedback": [],
        "visible_elements": [],
    }


def _edge(edge_id: str, fr: str, to: str, kind: str = "progress", texts: list[str] | None = None) -> dict:
    texts = texts or ["Continue"]
    step = {
        "action_role": "commit",
        "action_text": texts,
        "source_group_id": "g1",
        "source_screen_intent_id": None,
    }
    return {
        "edge_id": edge_id,
        "from_state": fr,
        "to_state": to,
        "edge_kind": kind,
        "scenario_role": "core",
        "action_sequence": [step],
        "confidence": "high",
        "edge_score": 90.0,
        "edge_risk_flags": [],
        "alternative_action_sequences": [],
        "context_parameters": [],
        "source_visible_evidence": [],
        "target_visible_evidence": [],
    }


def test_compose_preserves_transition_edge_order() -> None:
    catalog = [_state("A"), _state("B"), _state("C", oc="success")]
    cands = [
        _edge("e_ab", "A", "B"),
        _edge("e_bc", "B", "C", kind="success_terminal"),
        _edge("e_wrong", "B", "A"),
    ]
    flows = [
        {
            "flow_id": "flow1",
            "flow_name": "Goal flow",
            "flow_type": "ordered_sequence",
            "user_goal": "Complete booking",
            "ordered_states": ["A", "B", "C"],
            "transition_edge_ids": ["e_ab", "e_bc"],
            "alternative_outcome_edge_ids": [],
            "transition_id_by_candidate_edge_id": {
                "e_ab": "t_ab",
                "e_bc": "t_bc",
                "e_wrong": "t_w",
            },
        }
    ]
    fdr = {
        "candidate_flows": flows,
        "report": {"candidate_edges": cands},
        "edge_decisions": [
            {
                "candidate_edge_id": "e_ab",
                "decision": "accepted",
                "bucket": "direct_transition",
                "reason_code": "selected_high_score_edge",
                "evidence_level": "strong",
            },
            {
                "candidate_edge_id": "e_bc",
                "decision": "accepted",
                "bucket": "direct_transition",
                "reason_code": "selected_high_score_edge",
                "evidence_level": "strong",
            },
        ],
    }

    cfs, _unresolved = bsvc._compose_flows_from_discovery(fdr, catalog)
    mains = [c for c in cfs if "cf_main" in c.get("composed_flow_id", "")]
    assert len(mains) == 1
    cf = mains[0]
    assert cf["composition_method"] == "agent4_selected_edges"
    seq = cf["edge_sequence"]
    assert [e["candidate_edge_id"] for e in seq] == ["e_ab", "e_bc"]
    assert cf["user_goal"] == "Complete booking"
    assert cf["confidence"] == "high"


def test_broken_agent4_chain_emits_dfs_fallback() -> None:
    catalog = [_state("A"), _state("B", oc="success"), _state("C", oc="success")]
    cands = [
        _edge("e_ab", "A", "B"),
        _edge("e_ac", "A", "C", kind="success_terminal"),
    ]
    flows = [
        {
            "flow_id": "fbrk",
            "flow_name": "Broken ordering",
            "flow_type": "ordered_sequence",
            "user_goal": "",
            "ordered_states": ["A", "B", "C"],
            "transition_edge_ids": ["e_ab", "e_ac"],
            "alternative_outcome_edge_ids": [],
            "transition_id_by_candidate_edge_id": {"e_ab": "t1", "e_ac": "t2"},
        }
    ]
    fdr = {
        "candidate_flows": flows,
        "report": {"candidate_edges": cands},
        "edge_decisions": [],
    }
    cfs, unresolved = bsvc._compose_flows_from_discovery(fdr, catalog)
    mains = [c for c in cfs if "cf_main" in c.get("composed_flow_id", "")]
    assert len(mains) == 1
    assert mains[0]["composition_method"] == "backend_dfs_fallback"
    assert any("continuous" in (u.reason or "").lower() for u in unresolved)


def test_run_behaviour_contract_persists_with_mock_db() -> None:
    catalog = [_state("A"), _state("B", oc="success")]
    cands = [_edge("e_ab", "A", "B", kind="success_terminal")]
    flows = [
        {
            "flow_id": "frun",
            "flow_name": "RunFlow",
            "flow_type": "ordered_sequence",
            "user_goal": "Run goal",
            "ordered_states": ["A", "B"],
            "transition_edge_ids": ["e_ab"],
            "alternative_outcome_edge_ids": [],
            "transition_id_by_candidate_edge_id": {"e_ab": "t_run"},
        }
    ]
    fdr = {
        "candidate_flows": flows,
        "report": {"candidate_edges": cands},
        "edge_decisions": [],
    }

    db = MagicMock()

    def _result(rows: list) -> MagicMock:
        m = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = rows
        m.scalars.return_value = scalars_mock
        return m

    db.execute = AsyncMock(return_value=_result([]))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    out = asyncio.run(bsvc.run_behaviour_contract_builder(db, "run_12345", fdr, catalog))
    assert out["generation_summary"]["total_behaviour_intents"] >= 1
    bi = out["behaviour_intents"][0]
    assert bi["business_goal"] == "Run goal"
    assert "success outcome" in bi["expected_result"].lower()
    db.commit.assert_awaited()


def test_templates_and_infer_intent() -> None:
    er = {"_role": "negative_branch", "edge_kind": "warning"}
    assert (
        bsvc._infer_intent_type("error_branch", {"outcome_state_type": "neutral"}, er, None)
        == "negative"
    )
    r = bsvc._expected_result_from_templates({"outcome_state_type": "validation_error"}, None)
    assert "validation feedback" in r.lower()
