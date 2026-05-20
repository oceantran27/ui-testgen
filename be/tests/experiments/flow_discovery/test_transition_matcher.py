from __future__ import annotations

from experiments.flow_discovery.evaluator.metric_calculator import transition_prf_from_bundle
from experiments.flow_discovery.evaluator.transition_matcher import match_transitions
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthTransition


def test_strict_tp_and_relaxed_counters() -> None:
    gt_list = [
        GroundTruthTransition(
            gt_transition_id="g1",
            from_state_id="s1",
            to_state_id="s2",
            trigger_action_text="submit",
            outcome_type="success",
            proposal_source="x",
        ),
    ]
    pred_ok = [{"pred_transition_id": "p1", "from_state_id": "s1", "to_state_id": "s2", "trigger_action_text": "submit", "outcome_type": "success"}]
    b_ok = match_transitions(pred_ok, gt_list)
    assert transition_prf_from_bundle(b_ok, relaxed=False)[0] == 1
    assert transition_prf_from_bundle(b_ok, relaxed=True)[0] == 1

    pred_bad_outcome = [dict(pred_ok[0], outcome_type="error")]
    bb = match_transitions(pred_bad_outcome, gt_list)
    assert transition_prf_from_bundle(bb, relaxed=False)[1] >= 1  # FP strict path
    assert bb.relaxed_items[0].match_status == "true_positive"
    assert "wrong_outcome_type" in (bb.relaxed_items[0].error_tags or [])


def test_wrong_source_strict_fp_relaxed_fp() -> None:
    gt_list = [
        GroundTruthTransition(
            gt_transition_id="g1",
            from_state_id="s1",
            to_state_id="s2",
            trigger_action_text="tap",
            outcome_type="neutral",
            proposal_source="x",
        ),
    ]
    preds = [{"pred_transition_id": "p1", "from_state_id": "sx", "to_state_id": "s2", "trigger_action_text": "tap", "outcome_type": "neutral"}]
    bb = match_transitions(preds, gt_list)
    assert transition_prf_from_bundle(bb, relaxed=False)[1] >= 1
    assert transition_prf_from_bundle(bb, relaxed=True)[1] >= 1


def test_missing_transition_strict_fn() -> None:
    gt_list = [
        GroundTruthTransition(
            gt_transition_id="g1",
            from_state_id="s1",
            to_state_id="s2",
            trigger_action_text="tap",
            outcome_type="neutral",
            proposal_source="x",
        ),
    ]
    bb = match_transitions([], gt_list)
    assert len(bb.false_negatives_strict) == 1
    assert transition_prf_from_bundle(bb, relaxed=False)[2] == 1
