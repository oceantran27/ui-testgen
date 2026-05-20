"""Sprint 5 evaluator unit tests."""

from __future__ import annotations

from pathlib import Path

from experiments.flow_discovery.evaluator.evaluation_runner import run_evaluation
from experiments.flow_discovery.gt_converter.ground_truth_converter import convert_raw_package_to_draft
from experiments.flow_discovery.io_utils import read_json_document, write_json_document
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage


def _login_screen() -> dict:
    return {
        "state_id": "login_1",
        "screen_purpose": "login_page",
        "taxonomy": {"screen_type": "auth", "outcome_state_type": "neutral"},
        "visible_elements": [],
        "available_actions": [
            {"action_id": "login_btn", "action_type": "submit", "text": ["Login"]},
        ],
        "visible_feedback": [],
        "interaction_groups": [],
        "screen_intents": [],
    }


def _dash_screen() -> dict:
    return {
        "state_id": "dash_1",
        "screen_purpose": "dashboard",
        "taxonomy": {"screen_type": "dashboard", "outcome_state_type": "positive"},
        "visible_elements": [{"element_type": "heading", "text": ["Dashboard"]}],
        "available_actions": [],
        "visible_feedback": [],
        "interaction_groups": [],
        "screen_intents": [],
    }


def _env() -> RawFlowDiscoveryExperimentPackage:
    compressed = {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": [_login_screen(), _dash_screen()],
        "trace_index": {
            "login_1": {"source_image_id": "i1", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
            "dash_1": {"source_image_id": "i2", "ui_state_package_ref": "", "screen_intent_package_ref": ""},
        },
    }
    repaired = {
        "semantic_clusters": [],
        "candidate_flows": [
            {
                "flow_id": "f1",
                "flow_name": "login_ok",
                "flow_type": "ordered_sequence",
                "ordered_steps": [
                    {"state_id": "login_1", "next_trigger_action": {"action_id": "login_btn", "text": ["Login"]}},
                    {"state_id": "dash_1"},
                ],
            }
        ],
    }
    return RawFlowDiscoveryExperimentPackage(
        app_id="evaltest",
        run_id="r1",
        input_refs={},
        compressed_catalog_package=compressed,
        llm_discovery_catalog={},
        prompt_snapshot={},
        model_config_snapshot={},
        raw_model_output=repaired,
        repaired_model_output=None,
    )


def test_evaluation_result_schema_round_trip_nested_metrics() -> None:
    from experiments.flow_discovery.schemas.evaluation_schema import (
        BranchMetrics,
        ErrorMetrics,
        EvaluationMetricsNested,
        EvaluationResult,
        FlowMetrics,
        TransitionMetrics,
    )

    result = EvaluationResult(
        app_id="demoauth",
        run_id="run_test",
        metrics=EvaluationMetricsNested(
            transition_metrics=TransitionMetrics(strict_f1=0.5),
            flow_metrics=FlowMetrics(membership_macro_f1=0.8),
            branch_metrics=BranchMetrics(branch_f1=0.7),
            error_metrics=ErrorMetrics(invalid_transition_count=1),
        ),
    )
    again = EvaluationResult.model_validate_json(result.model_dump_json(round_trip=True))
    assert again.metrics.transition_metrics.strict_f1 == 0.5


def test_evaluator_strict_f1_perfect_on_same_pipeline(tmp_path: Path) -> None:
    env = _env()
    gt = convert_raw_package_to_draft(env)
    raw_path = tmp_path / "raw.json"
    gt_path = tmp_path / "gt.json"
    write_json_document(raw_path, env.model_dump(mode="json", round_trip=True))
    write_json_document(gt_path, gt.model_dump(mode="json", round_trip=True))
    out_dir = tmp_path / "eval_out"
    res = run_evaluation(
        app_id="evaltest",
        raw_output_path=raw_path,
        ground_truth_path=gt_path,
        out_dir=out_dir,
    )
    tm = res.metrics.transition_metrics
    assert tm.strict_f1 is not None
    assert tm.strict_f1 == 1.0
    assert (out_dir / "evaluation_result.json").is_file()
    assert (out_dir / "evaluation_report.md").is_file()
    assert (out_dir / "evaluation_summary.csv").is_file()


def test_flow_ordering_accuracy_two_thirds(tmp_path: Path) -> None:
    """GT A→B→C vs pred flow A→C→B yields 2/3 pairwise order constraints."""
    from experiments.flow_discovery.evaluator.flow_matcher import evaluate_flows

    doc = {
        "schema_version": "ground_truth_flow_package_v2",
        "app_id": "x",
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
    from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage

    gt = GroundTruthFlowPackage.model_validate(doc)
    pred_flows = [{"pred_flow_id": "pf1", "source_flow_id": "f1", "ordered_state_ids": ["A", "C", "B"]}]
    items = evaluate_flows(gt, [], pred_flows)
    assert len(items) == 1
    assert abs(float(items[0].ordering_accuracy or 0.0) - (2.0 / 3.0)) < 1e-6


def test_relaxed_f1_when_outcome_wrong(tmp_path: Path) -> None:
    env = _env()
    gt = convert_raw_package_to_draft(env)
    wrong = gt.model_dump(mode="python")
    if wrong["transitions"]:
        wrong["transitions"][0]["outcome_type"] = "error"
    from experiments.flow_discovery.schemas.ground_truth_schema import GroundTruthFlowPackage

    gt2 = GroundTruthFlowPackage.model_validate(wrong)
    raw_path = tmp_path / "raw.json"
    gt_path = tmp_path / "gt.json"
    write_json_document(raw_path, env.model_dump(mode="json", round_trip=True))
    write_json_document(gt_path, gt2.model_dump(mode="json", round_trip=True))
    res = run_evaluation(
        app_id="evaltest",
        raw_output_path=raw_path,
        ground_truth_path=gt_path,
        out_dir=tmp_path / "e2",
    )
    assert res.metrics.transition_metrics.strict_f1 == 0.0
    assert (res.metrics.transition_metrics.relaxed_f1 or 0.0) >= 1.0 - 1e-6


def test_evaluate_cli(tmp_path: Path) -> None:
    from experiments.flow_discovery.cli import main as cli_main

    env = _env()
    gt = convert_raw_package_to_draft(env)
    raw_path = tmp_path / "raw.json"
    gt_path = tmp_path / "gt.json"
    write_json_document(raw_path, env.model_dump(mode="json", round_trip=True))
    write_json_document(gt_path, gt.model_dump(mode="json", round_trip=True))
    out_dir = tmp_path / "ecli"
    code = cli_main(
        [
            "evaluate",
            "--app-id",
            "evaltest",
            "--raw-output",
            str(raw_path),
            "--ground-truth",
            str(gt_path),
            "--out-dir",
            str(out_dir),
        ],
    )
    assert code == 0
    data = read_json_document(out_dir / "evaluation_result.json")
    assert data["schema_version"] == "flow_discovery_evaluation_v2"