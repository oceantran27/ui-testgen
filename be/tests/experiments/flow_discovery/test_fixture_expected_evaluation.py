from __future__ import annotations

from pathlib import Path

from experiments.flow_discovery.evaluator.evaluation_runner import run_evaluation
from experiments.flow_discovery.io_utils import read_json_document


def test_demoauth_fixture_metrics_match_snapshotted_expectation(
    fixture_demoauth_dir: Path,
    tmp_path: Path,
) -> None:
    exp = read_json_document(fixture_demoauth_dir / "expected_evaluation_result.json")
    raw_path = fixture_demoauth_dir / "raw_model_output.json"
    gt_path = fixture_demoauth_dir / "ground_truth.reviewed.sample.json"
    out_eval = tmp_path / "eval_out"

    got = run_evaluation(
        app_id="demoauth",
        raw_output_path=raw_path,
        ground_truth_path=gt_path,
        out_dir=out_eval,
        run_id="fixture_assert",
    )
    gm = got.metrics.model_dump(mode="json", round_trip=True)
    for path in ("strict_f1", "relaxed_f1"):
        assert abs(float(gm["transition_metrics"][path]) - float(exp["metrics"]["transition_metrics"][path])) < 1e-9
