from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experiments.isolated_ui_coverage_eval.ground_truth import load_coverage_ground_truth
from experiments.isolated_ui_coverage_eval.matching import (
    extract_quoted_spans_from_when_and_lines,
    normalize_baseline_model_output_for_quotes,
    one_to_one_match_count,
)
from experiments.isolated_ui_coverage_eval.metrics import coverage_ratio, mean, pstdev
from experiments.test_scenario_title_eval.images import list_images_by_id

logger = logging.getLogger(__name__)

CSV_FIELDNAMES = [
    "id",
    "N_total",
    "C_proposed_raw_union_ids",
    "C_proposed_aligned",
    "Coverage_proposed",
    "stage1_gt_aligned",
    "stage1_gt_recall",
    "C_baseline_aligned",
    "Coverage_baseline",
    "stage1_control_count",
    "scoped_control_count",
    "baseline_when_and_quotes_count",
    "match_threshold",
    "stage1_llm_seconds",
    "stage2_llm_seconds",
    "baseline_llm_seconds",
    "unmatched_gt_proposed_json",
    "unmatched_gt_baseline_json",
    "unmatched_gt_stage1_json",
]


def default_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


def _cell_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _control_display_variants(ctrl: Any) -> list[str]:
    from app.schemas.ui_extraction import UIExtractedControl

    if not isinstance(ctrl, UIExtractedControl):
        return []
    out: list[str] = []
    if ctrl.label.strip():
        out.append(ctrl.label.strip())
    v = ctrl.value.strip()
    if v and v not in out:
        out.append(v)
    return out


def _candidate_strings_from_extraction_controls(controls: list[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for c in controls:
        for s in _control_display_variants(c):
            key = s.casefold()
            if key not in seen:
                seen.add(key)
                ordered.append(s)
    return ordered


def _union_control_ids_from_intents(intents_body: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in intents_body:
        ids = row.get("control_ids")
        if not isinstance(ids, list):
            continue
        for x in ids:
            if not isinstance(x, str):
                continue
            cid = x.strip()
            if cid and cid not in seen:
                seen.add(cid)
                out.append(cid)
    return out


def _candidates_for_control_ids(
    control_ids: list[str],
    id_to_control: dict[str, Any],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for cid in control_ids:
        c = id_to_control.get(cid)
        if c is None:
            continue
        for s in _control_display_variants(c):
            key = s.casefold()
            if key not in seen:
                seen.add(key)
                ordered.append(s)
    return ordered


@dataclass
class RunConfig:
    ground_truth_path: Path
    images_dir: Path
    match_threshold: float
    stage1_model: str
    stage2_model: str
    baseline_model: str
    out_csv: Path
    out_json: Path
    out_summary_json: Path
    skip_proposed: bool = False
    skip_baseline: bool = False
    id_min: int | None = None
    id_max: int | None = None


def _process_one_image(
    eid: int,
    image_path: Path,
    *,
    gt_elements: list[str],
    cfg: RunConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (detail_blob, csv_row)."""
    from app.schemas.ui_extraction import UIExtractionResult
    from app.services.baseline_gherkin_coverage_service import generate_baseline_gherkin_gemini_sync
    from app.services.ui_extraction_payload import filter_scoped_ui_extraction, user_intent_input_to_minified_json
    from app.services.ui_extraction_service import extract_ui_extraction_gemini_sync
    from app.services.user_intent_service import generate_user_intents_openai_sync

    n_total = len(gt_elements)
    image_id_str = str(eid)

    row: dict[str, str] = {
        "id": str(eid),
        "N_total": str(n_total),
        "C_proposed_raw_union_ids": "",
        "C_proposed_aligned": "",
        "Coverage_proposed": "",
        "stage1_gt_aligned": "",
        "stage1_gt_recall": "",
        "C_baseline_aligned": "",
        "Coverage_baseline": "",
        "stage1_control_count": "",
        "scoped_control_count": "",
        "baseline_when_and_quotes_count": "",
        "match_threshold": f"{cfg.match_threshold:.4f}",
        "stage1_llm_seconds": "",
        "stage2_llm_seconds": "",
        "baseline_llm_seconds": "",
        "unmatched_gt_proposed_json": "",
        "unmatched_gt_baseline_json": "",
        "unmatched_gt_stage1_json": "",
    }

    detail: dict[str, Any] = {
        "id": eid,
        "image_path": str(image_path),
        "N_total": n_total,
        "ground_truth_elements": list(gt_elements),
    }

    ui_full: UIExtractionResult | None = None
    scoped = None
    intents_payload: dict[str, Any] | None = None
    baseline_text: str | None = None

    if not cfg.skip_proposed:
        ui_full, stage1_sec = extract_ui_extraction_gemini_sync(str(image_path), cfg.stage1_model)
        scoped = filter_scoped_ui_extraction(ui_full)
        scoped_candidates = _candidate_strings_from_extraction_controls(scoped.controls)
        st1_match, st1_unmatched = one_to_one_match_count(
            gt_elements,
            scoped_candidates,
            threshold=cfg.match_threshold,
        )
        row["stage1_gt_aligned"] = str(st1_match)
        row["stage1_gt_recall"] = f"{coverage_ratio(st1_match, n_total):.6f}"
        row["stage1_control_count"] = str(len(ui_full.controls))
        row["scoped_control_count"] = str(len(scoped.controls))
        row["stage1_llm_seconds"] = f"{stage1_sec:.6f}"
        row["unmatched_gt_stage1_json"] = _cell_json(st1_unmatched)

        minified = user_intent_input_to_minified_json(scoped)
        t_iso0 = time.perf_counter()
        intents = generate_user_intents_openai_sync(image_id_str, minified, cfg.stage2_model)
        row["stage2_llm_seconds"] = f"{time.perf_counter() - t_iso0:.6f}"

        intents_payload = intents.model_dump(mode="json")
        detail["ui_extraction_full"] = ui_full.model_dump(mode="json")
        detail["ui_extraction_scoped"] = scoped.model_dump(mode="json")
        detail["user_intents_result"] = intents_payload

        id_to_control = {c.id: c for c in scoped.controls}
        union_ids = _union_control_ids_from_intents(intents_payload.get("user_intents", []))
        row["C_proposed_raw_union_ids"] = str(len(union_ids))
        prop_cands = _candidates_for_control_ids(union_ids, id_to_control)
        prop_match, prop_unmatched = one_to_one_match_count(
            gt_elements,
            prop_cands,
            threshold=cfg.match_threshold,
        )
        row["C_proposed_aligned"] = str(prop_match)
        row["Coverage_proposed"] = f"{coverage_ratio(prop_match, n_total):.6f}"
        row["unmatched_gt_proposed_json"] = _cell_json(prop_unmatched)
        detail["C_proposed_raw_union_ids"] = union_ids
        detail["C_proposed_aligned"] = prop_match
        detail["coverage_proposed"] = coverage_ratio(prop_match, n_total)
    else:
        row["stage1_gt_aligned"] = ""
        row["stage1_gt_recall"] = ""
        row["unmatched_gt_stage1_json"] = _cell_json([])
        row["unmatched_gt_proposed_json"] = _cell_json([])

    if not cfg.skip_baseline:
        baseline_text, base_sec = generate_baseline_gherkin_gemini_sync(str(image_path), cfg.baseline_model)
        row["baseline_llm_seconds"] = f"{base_sec:.6f}"
        quotes = extract_quoted_spans_from_when_and_lines(
            normalize_baseline_model_output_for_quotes(baseline_text)
        )
        row["baseline_when_and_quotes_count"] = str(len(quotes))
        base_match, base_unmatched = one_to_one_match_count(
            gt_elements,
            quotes,
            threshold=cfg.match_threshold,
        )
        row["C_baseline_aligned"] = str(base_match)
        row["Coverage_baseline"] = f"{coverage_ratio(base_match, n_total):.6f}"
        row["unmatched_gt_baseline_json"] = _cell_json(base_unmatched)
        detail["baseline_gherkin"] = baseline_text
        detail["baseline_when_and_quotes"] = quotes
        detail["C_baseline_aligned"] = base_match
        detail["coverage_baseline"] = coverage_ratio(base_match, n_total)
    else:
        row["baseline_when_and_quotes_count"] = ""
        row["unmatched_gt_baseline_json"] = _cell_json([])

    return detail, row


def _write_checkpoint(
    cfg: RunConfig,
    json_rows: list[dict[str, Any]],
    csv_rows: list[dict[str, Any]],
    *,
    log: bool = True,
) -> None:
    _atomic_write_text(
        cfg.out_json,
        json.dumps(json_rows, ensure_ascii=False, indent=2) + "\n",
    )
    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
    w.writeheader()
    w.writerows(csv_rows)
    _atomic_write_text(cfg.out_csv, sio.getvalue())
    if log:
        logger.info("Checkpoint: %d row(s) -> %s, %s", len(csv_rows), cfg.out_json, cfg.out_csv)


def _write_summary(
    cfg: RunConfig,
    csv_rows: list[dict[str, Any]],
) -> None:
    def _col(name: str) -> list[float]:
        out: list[float] = []
        for r in csv_rows:
            v = r.get(name, "").strip()
            if not v:
                continue
            try:
                out.append(float(v))
            except ValueError:
                continue
        return out

    proposed = _col("Coverage_proposed")
    baseline = _col("Coverage_baseline")
    recall = _col("stage1_gt_recall")
    summary = {
        "n_images": len(csv_rows),
        "match_threshold": cfg.match_threshold,
        "coverage_proposed_mean": mean(proposed),
        "coverage_proposed_pstdev": pstdev(proposed),
        "coverage_baseline_mean": mean(baseline),
        "coverage_baseline_pstdev": pstdev(baseline),
        "stage1_gt_recall_mean": mean(recall),
        "stage1_gt_recall_pstdev": pstdev(recall),
    }
    _atomic_write_text(
        cfg.out_summary_json,
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    logger.info("Summary -> %s", cfg.out_summary_json)


async def run_experiment_async(cfg: RunConfig) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    gt_by_id = load_coverage_ground_truth(cfg.ground_truth_path)
    all_pairs = list_images_by_id(cfg.images_dir)
    if not all_pairs:
        raise SystemExit(
            f"No images found under {cfg.images_dir} (expected names like 1.png, 2.jpg)."
        )

    pairs = [
        (eid, p)
        for eid, p in all_pairs
        if (cfg.id_min is None or eid >= cfg.id_min) and (cfg.id_max is None or eid <= cfg.id_max)
    ]
    if not pairs:
        raise SystemExit(
            f"No images in id range under {cfg.images_dir}."
        )

    json_rows: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    failed_ids: list[int] = []

    try:
        for eid, image_path in pairs:
            if eid not in gt_by_id:
                logger.warning(
                    "Skipping id=%s: no entry in coverage ground truth (%s).",
                    eid,
                    cfg.ground_truth_path,
                )
                continue
            gt = gt_by_id[eid]
            try:
                detail, row = await asyncio.to_thread(
                    _process_one_image,
                    eid,
                    image_path,
                    gt_elements=gt,
                    cfg=cfg,
                )
                json_rows.append(detail)
                csv_rows.append(row)
                logger.info(
                    "id=%s coverage_proposed=%s coverage_baseline=%s stage1_recall=%s",
                    eid,
                    row.get("Coverage_proposed") or "—",
                    row.get("Coverage_baseline") or "—",
                    row.get("stage1_gt_recall") or "—",
                )
                _write_checkpoint(cfg, json_rows, csv_rows, log=True)
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                failed_ids.append(eid)
                logger.exception("Failed id=%s (%s): %s", eid, image_path, exc)
    except KeyboardInterrupt:
        logger.warning(
            "Interrupted (Ctrl+C). Writing latest checkpoint: %d completed row(s).",
            len(csv_rows),
        )
        if csv_rows or json_rows:
            _write_checkpoint(cfg, json_rows, csv_rows, log=True)
            _write_summary(cfg, csv_rows)
        else:
            logger.warning("No completed image rows to persist.")
        sys.exit(130)

    logger.info(
        "Run complete: %d row(s) written, %d id(s) failed (see logs above).",
        len(csv_rows),
        len(failed_ids),
    )
    if failed_ids:
        logger.info("Failed ids: %s", failed_ids)
    if csv_rows:
        _write_summary(cfg, csv_rows)

    missing_gt_files = set(gt_by_id.keys()) - {i for i, _ in all_pairs}
    if missing_gt_files:
        logger.warning(
            "Ground truth ids with no image file (sample): %s",
            sorted(missing_gt_files)[:20],
        )


def run_experiment(cfg: RunConfig) -> None:
    asyncio.run(run_experiment_async(cfg))


__all__ = ["RunConfig", "CSV_FIELDNAMES", "run_experiment", "default_timestamp"]
