from __future__ import annotations

from experiments.flow_discovery.gt_converter.branch_group_converter import build_branch_groups
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthTransition


def _sample_tx(gt_id: str, anchor: str, to_id: str, outcome: str) -> GroundTruthTransition:
    return GroundTruthTransition(
        gt_transition_id=gt_id,
        from_state_id=anchor,
        to_state_id=to_id,
        trigger_action_id="b",
        trigger_action_text="go",
        outcome_type=outcome,
        proposal_source="test",
    )


def test_branch_group_requires_at_least_two_outgoing_same_anchor_trigger_key() -> None:
    txs = [
        _sample_tx("t1", "anchor", "dash", "positive"),
        _sample_tx("t2", "other", "x", "positive"),
    ]
    groups = build_branch_groups("x", txs)
    assert groups == []

    txs2 = txs + [_sample_tx("t3", "anchor", "err", "error")]
    groups2 = build_branch_groups("x", txs2)
    assert len(groups2) == 1
    assert len(groups2[0].alternative_transition_ids) >= 2

