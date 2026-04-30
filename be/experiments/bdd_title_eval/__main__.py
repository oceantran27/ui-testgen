"""
CLI for BDD title evaluation.

Run from the ``be/`` directory so package resolution works::

    cd be
    python -m experiments.bdd_title_eval --help

Or with explicit PYTHONPATH::

    set PYTHONPATH=.
    python -m experiments.bdd_title_eval --threshold 0.75

Requires ``GEMINI_API_KEY`` (and usual app env) for BDD generation (default model: gemini-2.5-pro).

Outputs (CSV, model_output JSON, optional raw) are checkpointed to disk after each
successfully processed image; Ctrl+C saves the latest completed rows and exits with code 130.
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

    from experiments.bdd_title_eval.run import default_timestamp

    ts = default_timestamp()

    p = argparse.ArgumentParser(
        description=(
            "Evaluate BDD scenario titles against ground_truth.json using embedding similarity. "
            "Iterates image files in data/images (names like 1.png), calls bdd_happy_path_service, "
            "and writes CSV + model_output JSON. Checkpoints after each image; safe to interrupt with Ctrl+C. "
            "Optional id range; errors on a single id are logged and skipped so the run continues."
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
        default=0.75,
        help="Cosine similarity threshold for matching a GT title to a model title (default: 0.75)",
    )
    p.add_argument(
        "--bdd-model",
        type=str,
        default="gemini-2.5-pro",
        metavar="ID",
        help="Model id for bdd_happy_path_service.generate (default: gemini-2.5-pro)",
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
        help=f"Output CSV path (default: {default_data}/bdd_title_eval_<timestamp>.csv)",
    )
    p.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help=f"Output model_output JSON (default: {default_data}/model_output_<timestamp>.json)",
    )
    p.add_argument(
        "--save-raw",
        action="store_true",
        help="Also write model_output_raw_<timestamp>.json with full BddHappyPathResult per id",
    )
    args = p.parse_args()
    if args.id_min is not None and args.id_max is not None and args.id_min > args.id_max:
        p.error("--id-min must be less than or equal to --id-max")

    out_csv = args.out_csv
    out_json = args.out_json
    if out_csv is None:
        out_csv = default_data / f"bdd_title_eval_{ts}.csv"
    if out_json is None:
        out_json = default_data / f"model_output_{ts}.json"
    out_raw = default_data / f"model_output_raw_{ts}.json" if args.save_raw else None

    from experiments.bdd_title_eval.run import RunConfig, run_experiment

    cfg = RunConfig(
        ground_truth_path=args.ground_truth.resolve(),
        images_dir=args.images_dir.resolve(),
        threshold=args.threshold,
        encoder_model=args.encoder,
        device=args.device,
        out_csv=out_csv.resolve(),
        out_json=out_json.resolve(),
        save_raw=args.save_raw,
        out_raw=out_raw.resolve() if out_raw else None,
        bdd_model=args.bdd_model,
        id_min=args.id_min,
        id_max=args.id_max,
    )
    run_experiment(cfg)


if __name__ == "__main__":
    main()
