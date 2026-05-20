from __future__ import annotations

import shutil
from pathlib import Path

from experiments.flow_discovery.cli import main as cli_main


def test_run_one_cli_skip_raw_capture_writes_three_artifacts(tmp_path: Path, fixture_demoauth_dir: Path) -> None:
    wd = tmp_path / "workspace"
    wd.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_demoauth_dir / "raw_model_output.json", wd / "raw_model_output.json")
    shutil.copy(fixture_demoauth_dir / "ground_truth.reviewed.sample.json", wd / "ground_truth.reviewed.json")

    cat = fixture_demoauth_dir / "compressed_catalog_package.json"

    rc = cli_main(
        [
            "run-one",
            "--app-id",
            "demoauth",
            "--compressed-catalog",
            str(cat.resolve()),
            "--work-dir",
            str(wd),
            "--skip-raw-capture",
        ],
    )
    assert rc == 0

    eval_dir = wd / "evaluation"
    assert (eval_dir / "evaluation_result.json").is_file()
    assert (eval_dir / "evaluation_report.md").is_file()
    assert (eval_dir / "evaluation_summary.csv").is_file()
    text = (eval_dir / "evaluation_report.md").read_text(encoding="utf-8")
    assert "# Flow Discovery Evaluation — demoauth" in text

