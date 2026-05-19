"""Module 3: evaluate UI state extraction (raw outputs vs temp ground truth)."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from app.core.logging import logger

from experiments.ui_state_extraction import config
from experiments.ui_state_extraction.schemas.evaluation_metric_schema import DatasetSummary
from experiments.ui_state_extraction.services.evaluation_dataset_loader_service import (
    dry_run_stats,
    load_evaluation_dataset,
)
from experiments.ui_state_extraction.services.experiment_debug_log_service import (
    append_module3_event,
    new_debug_log_path,
)
from experiments.ui_state_extraction.services.evaluation_report_service import (
    category_metric_csv_rows,
    metrics_summary_csv_rows,
    per_image_csv_rows,
    write_csv,
    write_evaluation_summary_json,
    write_markdown_report,
    write_per_image_json,
)
from experiments.ui_state_extraction.services.metric_calculation_service import (
    evaluate_pair,
    micro_macro_from_per_image,
)
from experiments.ui_state_extraction.services.prediction_normalizer_service import (
    normalize_raw_model_output,
)
from experiments.ui_state_extraction.services.raw_output_persistence_service import path_for_manifest


def _skip_reason_histogram(skipped: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(x.get("reason", "unknown")) for x in skipped))


def main() -> None:
    p = argparse.ArgumentParser(description="Module 3: UI state extraction evaluation")
    p.add_argument("--raw-output-dir", type=Path, default=config.RAW_OUTPUT_DIR)
    p.add_argument("--ground-truth-dir", type=Path, default=config.TEMP_GROUND_TRUTH_DIR)
    p.add_argument("--output-dir", type=Path, default=config.EVALUATION_REPORT_DIR)
    p.add_argument("--group-threshold", type=float, default=config.GROUP_MATCH_JACCARD_THRESHOLD)
    p.add_argument(
        "--include-debug",
        type=lambda x: str(x).lower() in ("1", "true", "yes"),
        default=config.INCLUDE_DEBUG_MATCH_TABLES,
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--write-debug-log",
        action="store_true",
        help="Append structured JSONL under reports/pipeline_debug/ (intent required_input explain, etc.)",
    )
    p.add_argument(
        "--debug-log-verbose",
        action="store_true",
        help="More fields in JSONL and extra logger lines",
    )
    args = p.parse_args()

    if args.dry_run:
        stats = dry_run_stats(raw_dir=args.raw_output_dir, gt_dir=args.ground_truth_dir)
        logger.info("Dry run stats: %s", stats)
        print(stats)
        return

    include_debug = bool(args.include_debug)

    write_dbg = bool(args.write_debug_log or config.EXPERIMENT_DEBUG_LOG_ENABLED)
    dbg_verbose = bool(args.debug_log_verbose or config.EXPERIMENT_DEBUG_LOG_VERBOSE)
    debug_log_path = new_debug_log_path(config.EXPERIMENT_DEBUG_LOG_DIR) if write_dbg else None
    if debug_log_path:
        logger.info("Module 3 debug log: %s", debug_log_path)

    loaded = load_evaluation_dataset(
        raw_dir=args.raw_output_dir,
        gt_dir=args.ground_truth_dir,
    )
    skipped_eval_all = list(loaded.skipped)
    skip_counts = _skip_reason_histogram(skipped_eval_all)

    results = []
    for pair in loaded.pairs:
        raw_out = pair.raw_doc.raw_model_output
        assert raw_out is not None
        pred = normalize_raw_model_output(raw_out)
        res = evaluate_pair(
            pred,
            pair.ground_truth,
            raw_out,
            group_jaccard_threshold=float(args.group_threshold),
            include_debug=include_debug,
        )
        if not include_debug:
            res.debug = {}
        results.append(res)
        if debug_log_path:
            append_module3_event(
                debug_log_path,
                pred=pred,
                gt=pair.ground_truth,
                per_image=res,
                group_jaccard_threshold=float(args.group_threshold),
                raw_output_path=path_for_manifest(pair.raw_path),
                temp_ground_truth_path=path_for_manifest(pair.gt_path),
                verbose_log=dbg_verbose,
            )

    micro, macro = micro_macro_from_per_image(results)
    n_eval = len(results)
    total_skipped = loaded.total_raw_outputs - n_eval

    dataset_summary = DatasetSummary(
        total_raw_outputs=loaded.total_raw_outputs,
        total_ground_truth_files=loaded.total_ground_truth_files,
        total_matched_pairs=loaded.total_matched_pairs,
        total_evaluated=n_eval,
        total_skipped=total_skipped,
        skip_reasons=skip_counts,
    )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    write_evaluation_summary_json(
        out / "evaluation_summary.json",
        schema_version=config.EVALUATION_SUMMARY_SCHEMA_VERSION,
        dataset_summary=dataset_summary,
        micro=micro,
        macro=macro,
        skipped_items=skipped_eval_all,
    )
    write_per_image_json(out / "evaluation_per_image.json", results)

    write_csv(out / "evaluation_summary.csv", metrics_summary_csv_rows(micro, macro, count=n_eval))
    write_csv(out / "evaluation_per_image.csv", per_image_csv_rows(results))
    for cat in ("element", "action", "feedback", "group", "intent"):
        write_csv(out / f"{cat}_metrics.csv", category_metric_csv_rows(cat, results))
    write_markdown_report(out / "evaluation_report.md", dataset_summary=dataset_summary, micro=micro)

    logger.info(
        "Evaluation complete: evaluated=%s total_skipped=%s report_dir=%s",
        n_eval,
        total_skipped,
        out,
    )


if __name__ == "__main__":
    main()
