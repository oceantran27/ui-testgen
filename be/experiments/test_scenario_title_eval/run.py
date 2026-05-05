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
from typing import Any, Literal

from .embeddings import encode_normalized, load_model
from .ground_truth import load_ground_truth
from .images import list_images_by_id
from .matching import greedy_cosine_match
from .metrics import per_image_prf1

logger = logging.getLogger(__name__)

CSV_BASE_FIELDNAMES = [
    "id",
    "GT",
    "MO",
    "Fail",
    "Excess",
    "Precision",
    "Recall",
    "F1_score",
]

CSV_FIELDNAMES = [*CSV_BASE_FIELDNAMES, "llm_seconds"]


@dataclass
class RunConfig:
    ground_truth_path: Path
    images_dir: Path
    threshold: float
    encoder_model: str
    device: str | None
    out_csv: Path
    out_json: Path
    save_raw: bool
    out_raw: Path | None
    # LLM backend for single_stage_test_scenario_service.generate (explicit routing vs name-prefix heuristic).
    provider: Literal["gemini", "openai"] = "gemini"
    # Scenario-generation model id for the chosen backend.
    generation_model: str = "gemini-2.5-flash"
    # Inclusive range on image id (stem). None = no bound.
    id_min: int | None = None
    id_max: int | None = None


def _titles_cell_json(titles: list[str]) -> str:
    """Single CSV cell: JSON array of strings, e.g. ``["a", "b"]`` or ``[]``."""
    return json.dumps(titles, ensure_ascii=False)


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write to ``path`` via a same-directory ``.tmp`` file then replace (best-effort atomic)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding=encoding)
    tmp.replace(path)


def _write_checkpoint(
    cfg: RunConfig,
    json_rows: list[dict[str, Any]],
    csv_rows: list[dict[str, Any]],
    raw_by_id: dict[str, Any],
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

    if cfg.save_raw and cfg.out_raw is not None:
        _atomic_write_text(
            cfg.out_raw,
            json.dumps(raw_by_id, ensure_ascii=False, indent=2) + "\n",
        )
    if log:
        n = len(csv_rows)
        logger.info("Checkpoint: %d row(s) -> %s, %s", n, cfg.out_json, cfg.out_csv)
        if cfg.save_raw and cfg.out_raw is not None:
            logger.info("Checkpoint raw: %s", cfg.out_raw)


async def _scenario_titles_for_image(
    image_path: Path,
    *,
    generation_model: str,
    provider: Literal["gemini", "openai"],
) -> tuple[list[str], Any, float]:
    from app.schemas.test_scenario_generation import TestScenarioSuite
    from app.services.single_stage_test_scenario_service import single_stage_test_scenario_service

    t0 = time.perf_counter()
    result: TestScenarioSuite = await single_stage_test_scenario_service.generate(
        str(image_path),
        model=generation_model,
        backend=provider,
    )
    elapsed = time.perf_counter() - t0
    return [s.title for s in result.scenarios], result, elapsed


async def run_experiment_async(cfg: RunConfig) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    gt_by_id = load_ground_truth(cfg.ground_truth_path)
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
            f"No images in id range "
            f"[{cfg.id_min if cfg.id_min is not None else 'min'}, {cfg.id_max if cfg.id_max is not None else 'max'}] "
            f"under {cfg.images_dir}."
        )
    if cfg.id_min is not None or cfg.id_max is not None:
        logger.info(
            "Id filter: min=%s max=%s (%d file(s) to process)",
            cfg.id_min,
            cfg.id_max,
            len(pairs),
        )

    logger.info("Scenario-gen provider=%s generation_model=%s", cfg.provider, cfg.generation_model)
    logger.info("Loading encoder: %s", cfg.encoder_model)
    model = load_model(cfg.encoder_model, device=cfg.device)

    json_rows: list[dict[str, Any]] = []
    raw_by_id: dict[str, Any] = {}
    csv_rows: list[dict[str, Any]] = []
    failed_ids: list[int] = []

    try:
        for eid, image_path in pairs:
            if eid not in gt_by_id:
                logger.warning(
                    "Skipping id=%s: no entry in ground truth (%s).", eid, cfg.ground_truth_path
                )
                continue
            gt = gt_by_id[eid]
            try:
                titles, suite_result, llm_seconds = await _scenario_titles_for_image(
                    image_path,
                    generation_model=cfg.generation_model,
                    provider=cfg.provider,
                )
                json_rows.append({"id": eid, "model_output": titles})
                if cfg.save_raw and cfg.out_raw is not None:
                    raw_by_id[str(eid)] = suite_result.model_dump(mode="json")

                g_emb = encode_normalized(model, gt)
                m_emb = encode_normalized(model, titles)
                match = greedy_cosine_match(gt, titles, g_emb, m_emb, cfg.threshold)
                m = per_image_prf1(match.tp, num_gt=len(gt), num_mo=float(len(titles)))

                csv_rows.append(
                    {
                        "id": eid,
                        "GT": _titles_cell_json(gt),
                        "MO": _titles_cell_json(titles),
                        "Fail": _titles_cell_json(match.fail),
                        "Excess": _titles_cell_json(match.excess),
                        "Precision": f"{m.precision:.6f}",
                        "Recall": f"{m.recall:.6f}",
                        "F1_score": f"{m.f1:.6f}",
                        "llm_seconds": f"{llm_seconds:.6f}",
                    }
                )
                logger.info(
                    "id=%s P=%.4f R=%.4f F1=%.4f (tp=%s |GT|=%s |MO|=%s)",
                    eid,
                    m.precision,
                    m.recall,
                    m.f1,
                    match.tp,
                    len(gt),
                    len(titles),
                )
                # Sync checkpoint immediately after this id (safe if Ctrl+C between iterations)
                _write_checkpoint(cfg, json_rows, csv_rows, raw_by_id, log=True)
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001 — skip single id, continue batch
                failed_ids.append(eid)
                logger.exception("Failed id=%s (%s): %s", eid, image_path, exc)
    except KeyboardInterrupt:
        logger.warning(
            "Interrupted (Ctrl+C). Writing latest checkpoint: %d completed row(s).",
            len(csv_rows),
        )
        if csv_rows or json_rows or raw_by_id:
            _write_checkpoint(cfg, json_rows, csv_rows, raw_by_id, log=True)
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

    missing_in_images = set(gt_by_id.keys()) - {eid for eid, _ in all_pairs}
    if missing_in_images:
        logger.warning(
            "Ground truth ids with no image file (sample): %s",
            sorted(missing_in_images)[:20],
        )


def run_experiment(cfg: RunConfig) -> None:
    asyncio.run(run_experiment_async(cfg))


def default_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
