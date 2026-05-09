from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.core.config import settings

from experiments.intent_coverage_judge.aggregate_metrics import (
    dedupe_mappings_by_generated,
    judge_lists_consistency_warnings,
    micro_recall_precision_f1,
    per_screen_mapping_counts,
    per_screen_mapping_sets,
    recall_precision_f1,
)
from experiments.intent_coverage_judge.io_loaders import (
    load_generated_dir,
    load_ground_truth_dir,
    pair_screens,
)
from experiments.intent_coverage_judge.judge_client import evaluate_single_screen_sync
from experiments.intent_coverage_judge.schemas import (
    GeneratedScreenFile,
    GroundTruthScreenFile,
    ScreenJudgeRecord,
)

logger = logging.getLogger(__name__)

CSV_FIELDNAMES = [
    "image_id",
    "n_gt",
    "n_gen",
    "n_mappings_raw",
    "n_mappings_deduped",
    "covered_gt",
    "mapped_gen",
    "recall",
    "precision",
    "f1",
    "missing_ground_truth_ids_json",
    "extra_generated_ids_json",
    "validation_warnings_json",
    "judge_seconds",
]


def default_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# Artifacts from this experiment (collect_baseline + judge CLI) live under data/result/<subdir>/<ts>/.
INTENT_COVERAGE_JUDGE_RESULT_SUBDIR = "intent_coverage_judge"


def default_intent_coverage_judge_run_dir(data_root: Path, timestamp: str | None = None) -> Path:
    """``{data_root}/result/intent_coverage_judge/<UTC>/`` (timestamp from :func:`default_timestamp` when omitted)."""
    ts = timestamp if timestamp is not None else default_timestamp()
    return data_root / "result" / INTENT_COVERAGE_JUDGE_RESULT_SUBDIR / ts


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


def _cell_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _fmt_float(x: float | None) -> str:
    if x is None:
        return ""
    return f"{x:.6f}"


@dataclass
class RunConfig:
    gt_dir: Path
    judge_model: str
    concurrency: int
    strict_pairing: bool
    skip_unpaired: bool
    out_csv: Path
    out_judge_json: Path
    out_summary_json: Path
    gen_dir: Path | None = None
    gen_by_id: dict[str, GeneratedScreenFile] | None = None

def _process_one_screen(
    image_id: str,
    gt_row: GroundTruthScreenFile,
    gen_row: GeneratedScreenFile,
    *,
    judge_model: str,
    client: OpenAI,
) -> tuple[dict[str, Any], dict[str, str], tuple[int, int, int, int]]:
    """Returns (judge_output_blob, csv_row, micro_row tuple)."""
    gt_ints = gt_row.ground_truth_intents
    gen_ints = gen_row.generated_intents
    gt_ids = {x.id for x in gt_ints}
    gen_ids = {x.id for x in gen_ints}
    n_gt, n_gen = len(gt_ids), len(gen_ids)

    evaluation, judge_sec = evaluate_single_screen_sync(
        image_id,
        gt_ints,
        gen_ints,
        model=judge_model,
        client=client,
    )
    deduped, dup_warnings = dedupe_mappings_by_generated(evaluation.mappings)
    covered, mapped, id_warnings = per_screen_mapping_counts(deduped, gt_ids, gen_ids)
    covered_set, mapped_set, _ = per_screen_mapping_sets(deduped, gt_ids, gen_ids)
    list_warnings = judge_lists_consistency_warnings(
        evaluation,
        gt_ids,
        gen_ids,
        covered_set,
        mapped_set,
    )
    all_warnings = [*dup_warnings, *id_warnings, *list_warnings]
    rec, prec, f1 = recall_precision_f1(covered, n_gt, mapped, n_gen)

    csv_row = {
        "image_id": image_id,
        "n_gt": str(n_gt),
        "n_gen": str(n_gen),
        "n_mappings_raw": str(len(evaluation.mappings)),
        "n_mappings_deduped": str(len(deduped)),
        "covered_gt": str(covered),
        "mapped_gen": str(mapped),
        "recall": _fmt_float(rec),
        "precision": _fmt_float(prec),
        "f1": _fmt_float(f1),
        "missing_ground_truth_ids_json": _cell_json(evaluation.missing_ground_truth_ids),
        "extra_generated_ids_json": _cell_json(evaluation.extra_generated_ids),
        "validation_warnings_json": _cell_json(all_warnings),
        "judge_seconds": f"{judge_sec:.6f}",
    }

    record = ScreenJudgeRecord(
        image_id=image_id,
        evaluation=evaluation,
        judge_seconds=judge_sec,
        validation_warnings=all_warnings,
    )
    micro_tuple = (n_gt, n_gen, covered, mapped)
    judge_blob = {
        "image_id": image_id,
        "record": record.model_dump(mode="json"),
    }
    return judge_blob, csv_row, micro_tuple


def _write_checkpoint(
    cfg: RunConfig,
    judge_by_id: dict[str, Any],
    csv_rows: list[dict[str, str]],
    *,
    log: bool = True,
) -> None:
    ordered = {k: judge_by_id[k] for k in sorted(judge_by_id.keys())}
    _atomic_write_text(
        cfg.out_judge_json,
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
    )
    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
    w.writeheader()
    w.writerows(csv_rows)
    _atomic_write_text(cfg.out_csv, sio.getvalue())
    if log:
        logger.info("Checkpoint: %d screen(s) -> %s", len(csv_rows), cfg.out_csv)


async def run_experiment_async(cfg: RunConfig) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not settings.OPENAI_API_KEY:
        raise SystemExit("OPENAI_API_KEY is not configured")

    gt_by_id = load_ground_truth_dir(cfg.gt_dir)
    if cfg.gen_by_id is not None:
        gen_by_id = cfg.gen_by_id
    elif cfg.gen_dir is not None:
        gen_by_id = load_generated_dir(cfg.gen_dir)
    else:
        raise SystemExit("RunConfig requires either gen_dir or gen_by_id.")
    paired, pair_errors = pair_screens(
        gt_by_id,
        gen_by_id,
        strict=cfg.strict_pairing,
        skip_unpaired=cfg.skip_unpaired,
    )
    if pair_errors:
        for e in pair_errors:
            logger.error("%s", e)
        if cfg.strict_pairing and not cfg.skip_unpaired:
            raise SystemExit(f"Pairing failed: {len(pair_errors)} issue(s). Use --skip-unpaired to run on intersection only.")

    if not paired:
        raise SystemExit("No paired image_id between ground truth and generated intents.")

    logger.info(
        "Paired screens: %d (judge_model=%s concurrency=%s)",
        len(paired),
        cfg.judge_model,
        cfg.concurrency,
    )

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    sem = asyncio.Semaphore(max(1, cfg.concurrency))
    lock = asyncio.Lock()
    judge_by_id: dict[str, Any] = {}
    csv_rows: list[dict[str, str]] = []
    micro_parts: list[tuple[int, int, int, int]] = []
    failed_ids: list[str] = []

    async def one(iid: str) -> None:
        async with sem:
            try:
                blob, row, mt = await asyncio.to_thread(
                    _process_one_screen,
                    iid,
                    gt_by_id[iid],
                    gen_by_id[iid],
                    judge_model=cfg.judge_model,
                    client=client,
                )
                async with lock:
                    judge_by_id[iid] = blob
                    csv_rows.append(row)
                    micro_parts.append(mt)
                    _write_checkpoint(
                        cfg,
                        judge_by_id,
                        sorted(csv_rows, key=lambda r: r["image_id"]),
                    )
                logger.info(
                    "image_id=%s recall=%s precision=%s f1=%s",
                    iid,
                    row["recall"] or "—",
                    row["precision"] or "—",
                    row["f1"] or "—",
                )
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                async with lock:
                    failed_ids.append(iid)
                logger.exception("Failed image_id=%s: %s", iid, exc)

    try:
        await asyncio.gather(*(one(iid) for iid in paired))
    except KeyboardInterrupt:
        logger.warning(
            "Interrupted. Checkpoint: %d completed screen(s).",
            len(csv_rows),
        )
        if csv_rows:
            _write_checkpoint(cfg, judge_by_id, sorted(csv_rows, key=lambda r: r["image_id"]))
        if micro_parts and csv_rows:
            _write_summary(cfg, micro_parts, csv_rows)
        sys.exit(130)

    logger.info(
        "Run complete: %d screen(s), %d failed.",
        len(csv_rows),
        len(failed_ids),
    )
    if failed_ids:
        logger.info("Failed image_ids: %s", failed_ids)

    _write_summary(cfg, micro_parts, csv_rows)


def _write_summary(
    cfg: RunConfig,
    micro_parts: list[tuple[int, int, int, int]],
    csv_data_rows: list[dict[str, str]],
) -> None:
    mr, mp, mf1 = micro_recall_precision_f1(micro_parts)
    summary = {
        "n_screens": len(micro_parts),
        "recall_micro": mr,
        "precision_micro": mp,
        "f1_micro": mf1,
        "judge_model": cfg.judge_model,
    }
    _atomic_write_text(
        cfg.out_summary_json,
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    logger.info(
        "Micro Recall=%s Precision=%s F1=%s -> %s",
        f"{mr:.6f}" if mr is not None else "—",
        f"{mp:.6f}" if mp is not None else "—",
        f"{mf1:.6f}" if mf1 is not None else "—",
        cfg.out_summary_json,
    )

    summary_row = {
        "image_id": "__MICRO_DATASET__",
        "n_gt": "",
        "n_gen": "",
        "n_mappings_raw": "",
        "n_mappings_deduped": "",
        "covered_gt": "",
        "mapped_gen": "",
        "recall": _fmt_float(mr),
        "precision": _fmt_float(mp),
        "f1": _fmt_float(mf1),
        "missing_ground_truth_ids_json": "[]",
        "extra_generated_ids_json": "[]",
        "validation_warnings_json": "[]",
        "judge_seconds": "",
    }
    ordered_rows = sorted(csv_data_rows, key=lambda r: r["image_id"])
    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
    w.writeheader()
    w.writerows(ordered_rows)
    w.writerow(summary_row)
    _atomic_write_text(cfg.out_csv, sio.getvalue())


def run_experiment(cfg: RunConfig) -> None:
    asyncio.run(run_experiment_async(cfg))


__all__ = [
    "RunConfig",
    "CSV_FIELDNAMES",
    "run_experiment",
    "default_timestamp",
    "INTENT_COVERAGE_JUDGE_RESULT_SUBDIR",
    "default_intent_coverage_judge_run_dir",
]