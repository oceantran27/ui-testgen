from __future__ import annotations



import asyncio

import csv

import io

import json

import logging

import sys

from dataclasses import dataclass

from pathlib import Path

from typing import Any, Literal



from experiments.bdd_title_eval.embeddings import encode_normalized, load_model

from experiments.bdd_title_eval.ground_truth import load_ground_truth

from experiments.bdd_title_eval.images import list_images_by_id

from experiments.bdd_title_eval.matching import greedy_cosine_match

from experiments.bdd_title_eval.metrics import per_image_prf1

from experiments.bdd_title_eval.run import CSV_BASE_FIELDNAMES, default_timestamp


CSV_FIELDNAMES = [*CSV_BASE_FIELDNAMES, "stage1_llm_seconds", "stage2_llm_seconds"]

logger = logging.getLogger(__name__)





@dataclass

class RunConfig:

    ground_truth_path: Path

    images_dir: Path

    threshold: float

    encoder_model: str

    device: str | None

    out_csv: Path

    out_json: Path

    out_agent1_json: Path

    pipeline: Literal["hybrid", "gemini", "openai"] = "hybrid"

    stage1_model: str | None = None

    stage2_model: str | None = None

    # Single OpenAI/Gemini id for pipeline gemini | openai (both stages)

    bdd_model: str | None = None

    id_min: int | None = None

    id_max: int | None = None





def _titles_cell_json(titles: list[str]) -> str:

    return json.dumps(titles, ensure_ascii=False)





def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:

    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_name(path.name + ".tmp")

    tmp.write_text(text, encoding=encoding)

    tmp.replace(path)





def _write_checkpoint(

    cfg: RunConfig,

    json_rows: list[dict[str, Any]],

    csv_rows: list[dict[str, Any]],

    agent1_by_id: dict[str, Any],

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

    _atomic_write_text(

        cfg.out_agent1_json,

        json.dumps(agent1_by_id, ensure_ascii=False, indent=2) + "\n",

    )

    if log:

        n = len(csv_rows)

        logger.info(

            "Checkpoint: %d row(s) -> %s, %s, %s",

            n,

            cfg.out_json,

            cfg.out_csv,

            cfg.out_agent1_json,

        )





async def _bdd_two_stage_titles_and_hierarchy(image_path: Path, *, cfg: RunConfig):

    from app.services.bdd_two_stage_service import bdd_two_stage_service



    if cfg.pipeline == "hybrid":

        bundle = await bdd_two_stage_service.generate_with_hierarchy(

            str(image_path),

            backend=None,

            stage1_model=cfg.stage1_model,

            stage2_model=cfg.stage2_model,

        )

    elif cfg.pipeline == "gemini":

        bundle = await bdd_two_stage_service.generate_with_hierarchy(

            str(image_path),

            model=cfg.bdd_model,

            backend="gemini",

        )

    else:

        bundle = await bdd_two_stage_service.generate_with_hierarchy(

            str(image_path),

            model=cfg.bdd_model,

            backend="openai",

        )

    titles = [s.title for s in bundle.bdd.scenarios]

    return titles, bundle, bundle.hierarchy.model_dump(mode="json")





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



    if cfg.pipeline == "hybrid":

        logger.info(

            "Module2 two-stage pipeline=hybrid stage1_override=%s stage2_override=%s (None => settings defaults)",

            cfg.stage1_model,

            cfg.stage2_model,

        )

    else:

        logger.info("Module2 two-stage pipeline=%s bdd_model=%s", cfg.pipeline, cfg.bdd_model)



    logger.info("Loading encoder: %s", cfg.encoder_model)

    model_enc = load_model(cfg.encoder_model, device=cfg.device)



    json_rows: list[dict[str, Any]] = []

    agent1_by_id: dict[str, Any] = {}

    csv_rows: list[dict[str, Any]] = []

    failed_ids: list[int] = []



    try:

        for eid, image_path in pairs:

            if eid not in gt_by_id:

                logger.warning(

                    "Skipping id=%s: no entry in ground truth (%s).",

                    eid,

                    cfg.ground_truth_path,

                )

                continue

            gt = gt_by_id[eid]

            try:

                titles, bundle, hier_dump = await _bdd_two_stage_titles_and_hierarchy(

                    image_path,

                    cfg=cfg,

                )

                json_rows.append({"id": eid, "model_output": titles})

                agent1_by_id[str(eid)] = hier_dump



                g_emb = encode_normalized(model_enc, gt)

                m_emb = encode_normalized(model_enc, titles)

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

                        "stage1_llm_seconds": f"{bundle.stage1_llm_seconds:.6f}",

                        "stage2_llm_seconds": f"{bundle.stage2_llm_seconds:.6f}",

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

                _write_checkpoint(cfg, json_rows, csv_rows, agent1_by_id, log=True)

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

        if csv_rows or json_rows or agent1_by_id:

            _write_checkpoint(cfg, json_rows, csv_rows, agent1_by_id, log=True)

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



    missing_in_images = set(gt_by_id.keys()) - {i for i, _ in all_pairs}

    if missing_in_images:

        logger.warning(

            "Ground truth ids with no image file (sample): %s",

            sorted(missing_in_images)[:20],

        )





def run_experiment(cfg: RunConfig) -> None:

    asyncio.run(run_experiment_async(cfg))





__all__ = ["RunConfig", "run_experiment", "default_timestamp"]

