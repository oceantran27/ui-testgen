"""
CLI: isolated UI coverage experiment (two-stage vs baseline Gherkin).

Run from ``be/``::

    cd be
    python -m experiments.isolated_ui_coverage_eval --help

**Ground truth** (``data/coverage_ground_truth.json``): JSON array of
``{"id": <int>, "elements": ["Label 1", ...]}``. See
``data/coverage_ground_truth.example.json`` and
``experiments/isolated_ui_coverage_eval/ground_truth.py`` for the annotation
convention (primary-layer vs full viewport — pick one and keep it consistent).

**Images**: same as other evals — ``data/images/<id>.png`` (integer stem).

Outputs under ``data/result/<UTC timestamp>/`` by default: detailed JSON per row,
CSV, and ``isolated_ui_coverage_summary_<ts>.json`` with mean/std. Checkpoint
after each successful image; Ctrl+C flushes and writes summary for completed rows.

Requires ``GEMINI_API_KEY`` (stage 1 + baseline) and ``OPENAI_API_KEY`` (stage 2
isolated scenarios), unless ``--skip-proposed`` or ``--skip-baseline``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _be_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_app_path() -> Path:
    root = _be_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def main() -> None:
    be = _ensure_app_path()
    from dotenv import load_dotenv

    load_dotenv(be / ".env")
    load_dotenv()

    default_data = be / "data"
    default_gt = default_data / "coverage_ground_truth.json"
    default_img = default_data / "images"

    from experiments.isolated_ui_coverage_eval.run import default_timestamp

    ts = default_timestamp()
    run_dir = default_data / "result" / ts

    p = argparse.ArgumentParser(
        description=(
            "Measure UI element coverage vs coverage_ground_truth.json: two-stage "
            "(Gemini ui-flat-v5 + OpenAI isolated scenarios / control_ids) vs baseline "
            "(Gemini plain Gherkin from baseline_single_stage_isolated_coverage_prompt)."
        )
    )
    p.add_argument(
        "--ground-truth",
        type=Path,
        default=default_gt,
        help=f"Path to coverage_ground_truth.json (default: {default_gt})",
    )
    p.add_argument(
        "--images-dir",
        type=Path,
        default=default_img,
        help=f"Directory of images named <id>.png etc. (default: {default_img})",
    )
    p.add_argument(
        "--id-min",
        type=int,
        default=None,
        metavar="N",
        help="Only process image ids with stem >= N (inclusive)",
    )
    p.add_argument(
        "--id-max",
        type=int,
        default=None,
        metavar="M",
        help="Only process image ids with stem <= M (inclusive)",
    )
    p.add_argument(
        "--match-threshold",
        type=float,
        default=0.86,
        help="Min difflib similarity (0-1) for GT ↔ candidate / quote matching (default: 0.86)",
    )
    p.add_argument(
        "--stage1-model",
        type=str,
        default="gemini-2.5-flash",
        metavar="ID",
        help="Gemini model for UI extraction (default: gemini-2.5-flash)",
    )
    p.add_argument(
        "--stage2-model",
        type=str,
        default="gpt-5-mini",
        metavar="ID",
        help="OpenAI model for isolated scenarios JSON (default: gpt-5-mini)",
    )
    p.add_argument(
        "--baseline-model",
        type=str,
        default="gemini-2.5-flash",
        metavar="ID",
        help="Gemini model for baseline Gherkin (default: gemini-2.5-flash)",
    )
    p.add_argument(
        "--skip-proposed",
        action="store_true",
        help="Only run baseline branch (no extraction / isolated scenarios)",
    )
    p.add_argument(
        "--skip-baseline",
        action="store_true",
        help="Only run two-stage proposed branch (no baseline Gherkin)",
    )
    p.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help=f"Output CSV (default: {run_dir}/isolated_ui_coverage_<timestamp>.csv)",
    )
    p.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help=f"Per-image detail JSON (default: {run_dir}/isolated_ui_coverage_detail_<timestamp>.json)",
    )
    p.add_argument(
        "--out-summary-json",
        type=Path,
        default=None,
        help=f"Aggregate summary JSON (default: {run_dir}/isolated_ui_coverage_summary_<timestamp>.json)",
    )
    args = p.parse_args()

    if args.id_min is not None and args.id_max is not None and args.id_min > args.id_max:
        p.error("--id-min must be <= --id-max")
    if args.skip_proposed and args.skip_baseline:
        p.error("Cannot set both --skip-proposed and --skip-baseline")

    out_csv = args.out_csv or run_dir / f"isolated_ui_coverage_{ts}.csv"
    out_json = args.out_json or run_dir / f"isolated_ui_coverage_detail_{ts}.json"
    out_summary = args.out_summary_json or run_dir / f"isolated_ui_coverage_summary_{ts}.json"

    from experiments.isolated_ui_coverage_eval.run import RunConfig, run_experiment

    cfg = RunConfig(
        ground_truth_path=args.ground_truth.resolve(),
        images_dir=args.images_dir.resolve(),
        match_threshold=args.match_threshold,
        stage1_model=args.stage1_model,
        stage2_model=args.stage2_model,
        baseline_model=args.baseline_model,
        out_csv=out_csv.resolve(),
        out_json=out_json.resolve(),
        out_summary_json=out_summary.resolve(),
        skip_proposed=args.skip_proposed,
        skip_baseline=args.skip_baseline,
        id_min=args.id_min,
        id_max=args.id_max,
    )
    run_experiment(cfg)


if __name__ == "__main__":
    main()
