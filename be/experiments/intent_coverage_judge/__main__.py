"""
CLI: LLM-as-judge semantic intent coverage (macro metrics).

Run from ``be/``::

    cd be
    python -m experiments.intent_coverage_judge --help

**Offline (pre-generated intents)**

- ``--gt-dir``: directory with ``ground_truth.json`` bundle (preferred) or per-screen ``*.json`` GT files.
- ``--gen-dir``: directory with per-screen generated JSON (*not* bundle).

**Auto-generation + eval**

- ``--mode baseline`` or ``--mode propose``: requires ``--gt-dir`` only; resolves images via ``--images-dir``,
  runs Gemini/OpenAI to build generated intents for every GT ``image_id``, then runs the judge.
  All outputs under ``{gt-dir}/eval/<UTC>/`` (CSV, judge JSON, summary, ``generated.json``, ``run_manifest.json``).

Pairing uses string ``image_id``. Offline: use ``--skip-unpaired`` for intersection-only pairing when key sets differ.

Outputs for offline runs default under ``data/result/intent_coverage_judge/<timestamp>/``.

Requires ``OPENAI_API_KEY`` for the judge (and Gemini keys when using ``--mode``). Default judge model: ``gpt-4o-mini``.

**Collect baseline** (single ``ground_truth.json`` bundle)::

    python -m experiments.intent_coverage_judge.collect_baseline
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _be_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_app_path() -> Path:
    root = _be_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    be = _ensure_app_path()
    from dotenv import load_dotenv

    load_dotenv(be / ".env")
    load_dotenv()

    default_data = be / "data"
    default_img = default_data / "images"
    from experiments.intent_coverage_judge.run import default_intent_coverage_judge_run_dir, default_timestamp

    ts_offline = default_timestamp()
    offline_run_dir = default_intent_coverage_judge_run_dir(default_data, ts_offline)

    p = argparse.ArgumentParser(
        description=(
            "Evaluate semantic intent coverage via OpenAI judge: map generated intents to "
            "ground-truth intents; aggregate micro Recall / Precision / F1."
        )
    )
    p.add_argument(
        "--gt-dir",
        type=Path,
        required=True,
        help="Directory containing ground_truth.json bundle or GT *.json files",
    )
    p.add_argument(
        "--gen-dir",
        type=Path,
        default=None,
        help="Directory of generated-intent *.json files (required when --mode is not set)",
    )
    p.add_argument(
        "--mode",
        type=str,
        choices=("baseline", "propose"),
        default=None,
        help=(
            "Run baseline (Gemini Gherkin) or propose (Gemini extract + OpenAI intents); "
            "implies auto-generation — do not pass --gen-dir."
        ),
    )
    p.add_argument(
        "--images-dir",
        type=Path,
        default=default_img,
        help=f"Image directory for --mode (default: {default_img})",
    )
    p.add_argument(
        "--baseline-model",
        type=str,
        default="gemini-2.5-flash",
        help="Gemini model for --mode baseline (default: gemini-2.5-flash)",
    )
    p.add_argument(
        "--stage1-model",
        type=str,
        default="gemini-2.5-flash",
        help="Gemini model for --mode propose stage 1 (default: gemini-2.5-flash)",
    )
    p.add_argument(
        "--stage2-model",
        type=str,
        default="gpt-5-mini",
        help="OpenAI model for --mode propose stage 2 (default: gpt-5-mini)",
    )
    p.add_argument(
        "--gen-concurrency",
        type=int,
        default=4,
        metavar="N",
        help="Max parallel generation calls when using --mode (default: 4)",
    )
    p.add_argument(
        "--judge-model",
        type=str,
        default="gpt-4o-mini",
        help="OpenAI model id for the judge (default: gpt-4o-mini)",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=10,
        metavar="N",
        help="Max concurrent OpenAI judge calls (default: 10)",
    )
    p.add_argument(
        "--no-strict",
        action="store_true",
        help="Do not exit on mismatched image_ids between dirs; evaluate intersection only",
    )
    p.add_argument(
        "--skip-unpaired",
        action="store_true",
        help="With mismatched dirs, only warn and evaluate intersection (implies non-fatal pairing)",
    )
    p.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help=(
            "CSV path (offline default: under data/result/intent_coverage_judge/<ts>/). "
            "Ignored when --mode is set (writes under gt-dir/eval/<ts>/)."
        ),
    )
    p.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Full judge JSON (same rules as --out-csv)",
    )
    p.add_argument(
        "--out-summary-json",
        type=Path,
        default=None,
        help="Micro metrics JSON (same rules as --out-csv)",
    )
    args = p.parse_args()

    if args.mode is not None and args.gen_dir is not None:
        p.error("--gen-dir cannot be used with --mode (generated in-process).")
    if args.mode is None and args.gen_dir is None:
        p.error("Either pass --mode baseline|propose or --gen-dir for offline pairing.")

    from experiments.intent_coverage_judge.io_loaders import load_ground_truth_dir
    from experiments.intent_coverage_judge.run import RunConfig, run_experiment

    gt_dir = args.gt_dir.resolve()

    if args.gen_dir is not None:
        out_csv = args.out_csv or offline_run_dir / "macro_metrics_report.csv"
        out_json = args.out_json or offline_run_dir / f"intent_judge_outputs_{ts_offline}.json"
        out_summary = args.out_summary_json or offline_run_dir / f"macro_metrics_summary_{ts_offline}.json"

        cfg = RunConfig(
            gt_dir=gt_dir,
            judge_model=args.judge_model.strip(),
            concurrency=max(1, args.concurrency),
            strict_pairing=not args.no_strict,
            skip_unpaired=args.skip_unpaired,
            out_csv=out_csv.resolve(),
            out_judge_json=out_json.resolve(),
            out_summary_json=out_summary.resolve(),
            gen_dir=args.gen_dir.resolve(),
            gen_by_id=None,
        )
        run_experiment(cfg)
        return

    gt_by_id = load_ground_truth_dir(gt_dir)
    if not gt_by_id:
        raise SystemExit(f"No ground truth loaded from {gt_dir}")

    eval_ts = default_timestamp()
    eval_dir = gt_dir / "eval" / eval_ts
    from experiments.intent_coverage_judge.generate_sidecar import generate_for_judge_async

    images_dir = args.images_dir.resolve()
    gen_by_id = asyncio.run(
        generate_for_judge_async(
            gt_by_id,
            images_dir,
            mode=args.mode,
            baseline_model=args.baseline_model.strip(),
            stage1_model=args.stage1_model.strip(),
            stage2_model=args.stage2_model.strip(),
            concurrency=max(1, args.gen_concurrency),
        )
    )

    screens_out = sorted(
        (gen_by_id[iid].model_dump(mode="json") for iid in gen_by_id),
        key=lambda r: (
            int(r["image_id"]) if str(r["image_id"]).isdigit() else float("inf"),
            str(r["image_id"]),
        ),
    )
    bundle = {
        "schema_version": "intent_coverage_judge_generated_bundle_v1",
        "mode": args.mode,
        "eval_ts": eval_ts,
        "baseline_model": args.baseline_model,
        "stage1_model": args.stage1_model,
        "stage2_model": args.stage2_model,
        "images_dir": str(images_dir),
        "screens": screens_out,
    }
    _atomic_write_json(eval_dir / "generated.json", bundle)

    manifest = {
        "eval_ts": eval_ts,
        "mode": args.mode,
        "gt_dir": str(gt_dir),
        "images_dir": str(images_dir),
        "baseline_model": args.baseline_model,
        "stage1_model": args.stage1_model,
        "stage2_model": args.stage2_model,
        "judge_model": args.judge_model,
        "judge_concurrency": args.concurrency,
        "gen_concurrency": args.gen_concurrency,
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(eval_dir / "run_manifest.json", manifest)

    out_csv = eval_dir / "macro_metrics_report.csv"
    out_json = eval_dir / f"intent_judge_outputs_{eval_ts}.json"
    out_summary = eval_dir / f"macro_metrics_summary_{eval_ts}.json"

    cfg = RunConfig(
        gt_dir=gt_dir,
        judge_model=args.judge_model.strip(),
        concurrency=max(1, args.concurrency),
        strict_pairing=not args.no_strict,
        skip_unpaired=args.skip_unpaired,
        out_csv=out_csv,
        out_judge_json=out_json,
        out_summary_json=out_summary,
        gen_dir=None,
        gen_by_id=gen_by_id,
    )
    run_experiment(cfg)


if __name__ == "__main__":
    main()
