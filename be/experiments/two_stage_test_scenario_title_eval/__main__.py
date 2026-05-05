"""
CLI for two-stage test scenario title evaluation (stage 1 UI extraction + stage 2 scenarios).

Run from the ``be/`` directory::

    cd be
    python -m experiments.two_stage_test_scenario_title_eval --help

Outputs under ``data/result/<UTC timestamp>/`` by default: CSV, model-output JSON (titles), and
stage-1 UI extraction JSON. Checkpointed after each successful image; Ctrl+C saves the latest
completed rows and exits with code 130.

Default ``--pipeline hybrid`` matches ``POST /api/v1/test-scenarios/from-image-bridged``: Gemini for
UI extraction plus GPT (from ``TWO_STAGE_STAGE2_MODEL`` / ``--stage2-model``) for scenarios.
Use ``--pipeline gemini`` or ``openai`` with ``--generation-model`` for a single-model two-stage backend.
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
    default_gt = default_data / "ground_truth.json"
    default_img = default_data / "images"

    from experiments.two_stage_test_scenario_title_eval.run import default_timestamp

    ts = default_timestamp()
    run_dir = default_data / "result" / ts

    p = argparse.ArgumentParser(
        description=(
            "Evaluate scenario titles for the two-stage pipeline against ground_truth.json using "
            "embedding similarity. Default pipeline uses Gemini vision (stage 1) plus GPT stage 2 (hybrid), "
            "same as two_stage_test_scenario_service with no overrides. Checkpoint after each image; Ctrl+C persists "
            "latest rows."
        )
    )
    p.add_argument(
        "--ground-truth",
        type=Path,
        default=default_gt,
        help=f"Path to ground_truth.json (default: {default_gt})",
    )
    p.add_argument(
        "--images-dir",
        type=Path,
        default=default_img,
        help=f"Directory of input images named <id>.png etc. (default: {default_img})",
    )
    p.add_argument(
        "--id-min",
        type=int,
        default=None,
        metavar="N",
        help="Only process image ids with stem >= N (inclusive; default: no lower bound)",
    )
    p.add_argument(
        "--id-max",
        type=int,
        default=None,
        metavar="M",
        help="Only process image ids with stem <= M (inclusive; default: no upper bound)",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.6,
        help="Cosine similarity threshold for matching a GT title to a model title (default: 0.6)",
    )
    p.add_argument(
        "--pipeline",
        choices=["hybrid", "gemini", "openai"],
        default="hybrid",
        help=(
            "hybrid (default)=Gemini LVLM stage 1 + GPT stage 2 via settings "
            "(TWO_STAGE_STAGE1_MODEL / TWO_STAGE_STAGE2_MODEL) or "
            "--stage1-model / --stage2-model; "
            "gemini|openai=both stages on one backend (--generation-model defaults gemini-2.5-flash vs gpt-5)."
        ),
    )
    p.add_argument(
        "--stage1-model",
        type=str,
        default=None,
        metavar="ID",
        help=(
            "Only with --pipeline hybrid: override Gemini stage 1 model (default from env "
            "TWO_STAGE_STAGE1_MODEL)."
        ),
    )
    p.add_argument(
        "--stage2-model",
        type=str,
        default=None,
        metavar="ID",
        help=(
            "Only with --pipeline hybrid: override stage 2 text model "
            "(default from env TWO_STAGE_STAGE2_MODEL, normally gpt-*)."
        ),
    )
    p.add_argument(
        "--generation-model",
        type=str,
        default=None,
        metavar="ID",
        help=(
            "Only with --pipeline gemini or openai: one model ID for vision + text two-stage "
            "(defaults: gemini-2.5-flash vs gpt-5). Not used when --pipeline hybrid."
        ),
    )
    p.add_argument(
        "--encoder",
        type=str,
        default="BAAI/bge-base-en-v1.5",
        help="sentence-transformers model id (default: BAAI/bge-base-en-v1.5)",
    )
    p.add_argument(
        "--device",
        type=str,
        default=None,
        help="Torch device e.g. cuda or cpu (default: auto)",
    )
    p.add_argument(
        "--out-csv",
        type=Path,
        default=None,
        help=(
            f"Output CSV path (default: {default_data}/result/<timestamp>/two_stage_test_scenario_title_eval_<timestamp>.csv)"
        ),
    )
    p.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help=(
            f"Titles JSON path (default: {default_data}/result/<timestamp>/two_stage_scenario_model_output_<timestamp>.json)"
        ),
    )
    p.add_argument(
        "--out-agent1-json",
        type=Path,
        default=None,
        help=(
            f"Stage 1 UI extraction JSON path (default: {default_data}/result/<timestamp>/stage1_ui_extraction_<timestamp>.json)"
        ),
    )
    args = p.parse_args()

    if args.id_min is not None and args.id_max is not None and args.id_min > args.id_max:
        p.error("--id-min must be less than or equal to --id-max")

    if args.pipeline == "hybrid":
        if args.generation_model is not None:
            p.error(
                "--generation-model cannot be used with --pipeline hybrid; use --stage1-model/--stage2-model"
            )
    else:
        if args.stage1_model is not None or args.stage2_model is not None:
            p.error(
                "--stage1-model and --stage2-model apply only with --pipeline hybrid; "
                "use --pipeline hybrid for split models or --generation-model here for a single-ID pipeline"
            )

    generation_model: str | None
    stage1_model: str | None = args.stage1_model
    stage2_model: str | None = args.stage2_model
    if args.pipeline == "hybrid":
        generation_model = None
    elif args.pipeline == "openai":
        generation_model = args.generation_model or "gpt-5"
    else:
        generation_model = args.generation_model or "gemini-2.5-flash"

    out_csv = args.out_csv
    out_json = args.out_json
    out_agent1 = args.out_agent1_json
    if out_csv is None:
        out_csv = run_dir / f"two_stage_test_scenario_title_eval_{ts}.csv"
    if out_json is None:
        out_json = run_dir / f"two_stage_scenario_model_output_{ts}.json"
    if out_agent1 is None:
        out_agent1 = run_dir / f"stage1_ui_extraction_{ts}.json"

    from experiments.two_stage_test_scenario_title_eval.run import RunConfig, run_experiment

    cfg = RunConfig(
        ground_truth_path=args.ground_truth.resolve(),
        images_dir=args.images_dir.resolve(),
        threshold=args.threshold,
        encoder_model=args.encoder,
        device=args.device,
        out_csv=out_csv.resolve(),
        out_json=out_json.resolve(),
        out_agent1_json=out_agent1.resolve(),
        pipeline=args.pipeline,
        stage1_model=stage1_model,
        stage2_model=stage2_model,
        generation_model=generation_model,
        id_min=args.id_min,
        id_max=args.id_max,
    )
    run_experiment(cfg)


if __name__ == "__main__":
    main()
