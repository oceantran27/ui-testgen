from __future__ import annotations

import json
import shutil
from pathlib import Path

from experiments.flow_discovery.cli import main as cli_main


def test_run_batch_cli_writes_summary_csv(tmp_path: Path, fixture_demoauth_dir: Path) -> None:
    wd = tmp_path / "workspace"
    wd.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_demoauth_dir / "raw_model_output.json", wd / "raw_model_output.json")
    shutil.copy(fixture_demoauth_dir / "ground_truth.reviewed.sample.json", wd / "ground_truth.reviewed.json")

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "apps": [
                    {
                        "app_id": "demoauth",
                        "compressed_catalog": str((fixture_demoauth_dir / "compressed_catalog_package.json").resolve()),
                        "ground_truth": str((fixture_demoauth_dir / "ground_truth.reviewed.sample.json").resolve()),
                        "work_dir": str(wd.resolve()),
                        "skip_raw_capture": True,
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / "batch_out"

    rc = cli_main(["run-batch", "--manifest", str(manifest.resolve()), "--out-dir", str(out_dir.resolve())])
    assert rc == 0

    csv_path = out_dir / "evaluation_summary.csv"
    assert csv_path.is_file()
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2
