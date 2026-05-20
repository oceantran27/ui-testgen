from __future__ import annotations

from experiments.flow_discovery.gt_converter.transition_converter import build_transitions
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthTransition


def _minimal_catalog_map() -> dict[str, str]:
    return {"a": "A", "b": "B", "c": "C"}


def _card(typ: str) -> dict[str, object]:
    return {
        "state_id": "",
        "screen_purpose": "p",
        "taxonomy": {"screen_type": "x", "outcome_state_type": typ},
        "visible_elements": [],
        "available_actions": [],
        "visible_feedback": [],
        "interaction_groups": [],
        "screen_intents": [],
    }


def _cards() -> dict[str, dict]:
    cards = {"b": _card("positive"), "c": _card("validation_error")}
    cards["b"]["state_id"] = "b"
    cards["c"]["state_id"] = "c"
    return cards


def test_ordered_step_transition_merges_target_taxonomy() -> None:
    model = {
        "candidate_flows": [
            {
                "flow_id": "pf",
                "ordered_steps": [
                    {"state_id": "a", "next_trigger_action": {"text": ["Go"]}},
                    {"state_id": "b"},
                ],
            }
        ]
    }

    txs = build_transitions("demo", model, {"a": "A", **{k: v for k, v in _minimal_catalog_map().items() if k != "a"}}, _cards())
    spine = next(t for t in txs if t.proposal_flow_id == "pf" and "ordered_steps" in t.proposal_source)
    assert spine.from_state_id == "A" and spine.to_state_id == "B"
    assert spine.outcome_type == "positive"


def test_alternative_transition_respects_explicit_outcome_role() -> None:
    model = {
        "candidate_flows": [
            {
                "flow_id": "br",
                "alternative_outcomes": [
                    {"from_state_id": "a", "to_state_id": "c", "outcome_role": "validation_error", "trigger_action": {"text": ["Tap"]}},
                ],
            }
        ]
    }
    txs = build_transitions("demo", model, {"a": "A", **{k: v for k, v in _minimal_catalog_map().items() if k != "a"}}, _cards())
    alt = txs[0]
    assert alt.outcome_type


def test_converter_skips_edges_when_anchor_missing_from_catalog_map() -> None:
    """Wrong source catalogue id ⇒ no usable transition."""
    model = {
        "candidate_flows": [
            {
                "flow_id": "pf",
                "ordered_steps": [
                    {"state_id": "missing", "next_trigger_action": {"text": ["Go"]}},
                    {"state_id": "b"},
                ],
            }
        ]
    }

    txs = build_transitions("demo", model, {"b": "B", "c": "C"}, _cards())
    assert txs == []
