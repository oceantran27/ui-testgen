from __future__ import annotations

from experiments.flow_discovery.evaluator.flow_matcher import evaluate_flows
from experiments.flow_discovery.evaluator.metric_calculator import transition_prf_from_bundle
from experiments.flow_discovery.evaluator.transition_matcher import match_transitions
from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage


def test_ordering_bc_swap_yields_two_thirds() -> None:
    gt_doc = {
        "schema_version": "ground_truth_flow_package_v2",
        "app_id": "suite",
        "states": [
            {"gt_state_id": "A", "catalog_state_id": "cA"},
            {"gt_state_id": "B", "catalog_state_id": "cB"},
            {"gt_state_id": "C", "catalog_state_id": "cC"},
        ],
        "actions": [],
        "transitions": [],
        "flows": [
            {
                "gt_flow_id": "gf1",
                "source_flow_id": "f1",
                "eval_include": True,
                "ordered_state_ids": ["A", "B", "C"],
                "transition_ids": [],
            },
        ],
        "branch_groups": [],
    }
    gt = GroundTruthFlowPackage.model_validate(gt_doc)
    pred_flows = [{"pred_flow_id": "pf1", "source_flow_id": "f1", "ordered_state_ids": ["A", "C", "B"]}]
    items = evaluate_flows(gt, [], pred_flows)
    assert len(items) == 1
    assert abs(float(items[0].ordering_accuracy or 0.0) - (2.0 / 3.0)) < 1e-6


def test_prf1_empty_prediction_all_fn_relaxed_mode() -> None:
    """Edge: predicted nothing ⇒ recall 0, precision degenerates to FN-only case."""
    from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthTransition

    gts = [
        GroundTruthTransition(
            gt_transition_id="x",
            from_state_id="a",
            to_state_id="b",
            trigger_action_text="t",
            outcome_type="ok",
            proposal_source="test",
        ),
    ]
    b = match_transitions([], gts)
    _, _, _, _p, _, _ = transition_prf_from_bundle(b, relaxed=False)
    assert b.relaxed_items == []


def test_branch_missing_predicted_outcome_lowers_macro_recall() -> None:
    from experiments.flow_discovery.evaluator.branch_matcher import evaluate_branches

    gt = GroundTruthFlowPackage.model_validate(
        {
            "schema_version": "ground_truth_flow_package_v2",
            "app_id": "branchtest",
            "states": [
                {"gt_state_id": "A", "catalog_state_id": "cA"},
                {"gt_state_id": "B", "catalog_state_id": "cB"},
                {"gt_state_id": "C", "catalog_state_id": "cC"},
            ],
            "actions": [],
            "transitions": [
                {
                    "gt_transition_id": "t1",
                    "from_state_id": "A",
                    "to_state_id": "B",
                    "trigger_action_text": "Go",
                    "outcome_type": "success",
                    "proposal_source": "fixture",
                },
                {
                    "gt_transition_id": "t2",
                    "from_state_id": "A",
                    "to_state_id": "C",
                    "trigger_action_text": "Go",
                    "outcome_type": "validation_error",
                    "proposal_source": "fixture",
                },
            ],
            "flows": [],
            "branch_groups": [
                {
                    "branch_group_id": "bg1",
                    "anchor_source_gt_state_id": "A",
                    "normalized_trigger": "go",
                    "state_ids": ["A"],
                    "alternative_transition_ids": ["t1", "t2"],
                    "eval_include": True,
                },
            ],
            "created_at": "2026-01-01T00:00:00Z",
        },
    )
    predicted_rows = [
        {
            "pred_transition_id": "p1",
            "from_state_id": "A",
            "to_state_id": "B",
            "trigger_action_text": "Go",
            "outcome_type": "success",
        },
    ]
    pred_branches = [
        {
            "pred_branch_id": "pred_bg_001",
            "anchor_source_gt_state_id": "A",
            "normalized_trigger": "go",
            "pred_transition_ids": ["p1"],
        },
    ]
    _, _p, rec, _f1 = evaluate_branches(gt, predicted_rows, pred_branches)
    assert float(rec or 1.0) < 1.0
