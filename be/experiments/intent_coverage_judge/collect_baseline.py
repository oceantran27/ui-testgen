"""
Collect baseline (Gemini vision) into one bundle file for ``--gt-dir``.

Writes a single ``ground_truth.json`` (see ``intent_coverage_judge.io_loaders.GROUND_TRUTH_BUNDLE_FILENAME``)
with ``screens[]``: each row matches ``GroundTruthScreenFile`` for manual refinement of ``intent_description``.

Run from ``be/``::

    cd be
    python -m experiments.intent_coverage_judge.collect_baseline

With explicit output directory::

    python -m experiments.intent_coverage_judge.collect_baseline --out-dir path/to/dir

Defaults: ``--images-dir data/images``, **first 10 images** by sorted integer id (``--limit``),
integer stems ``1.png``, ``2.jpg``. When ``--out-dir`` is omitted, writes under
``data/result/intent_coverage_judge/<UTC>/``.

Options ``--include-raw`` always embeds ``baseline_raw_response`` per screen; otherwise raw is stored
only if parsing fails or yields zero intents.

If any screen raises an exception during collection, ``ground_truth.json`` is **not** written.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.baseline_gherkin_coverage_service import generate_baseline_gherkin_gemini_sync

from experiments.intent_coverage_judge.io_loaders import GROUND_TRUTH_BUNDLE_FILENAME
from experiments.isolated_ui_coverage_eval.matching import strip_markdown_code_fence
from experiments.test_scenario_title_eval.images import list_images_by_id

logger = logging.getLogger(__name__)


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_baseline_response_to_generated_intents(raw: str) -> tuple[list[dict[str, str]], str | None]:
    """
    Parse baseline model output into rows with ``intent`` and ``gherkin`` (no ``id`` yet).

    Returns (list of {intent, gherkin}, error_message or None).
    """
    stripped = strip_markdown_code_fence(raw.strip())
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return [], f"json_decode: {exc}"
    if not isinstance(data, dict):
        return [], "root_not_object"
    ui = data.get("user_intents")
    if not isinstance(ui, list):
        return [], "missing_user_intents_array"
    out: list[dict[str, str]] = []
    for item in ui:
        if not isinstance(item, dict):
            continue
        intent = item.get("intent")
        gherkin = item.get("gherkin")
        if not isinstance(intent, str) or not intent.strip():
            continue
        gstr = gherkin if isinstance(gherkin, str) else ""
        out.append({"intent": intent.strip(), "gherkin": gstr.strip()})
    if not out and ui:
        return [], "user_intents_empty_after_parse"
    return out, None


def parsed_intent_rows_to_ground_truth_intents(body: list[dict[str, str]]) -> list[dict[str, str]]:
    """Turn parsed baseline rows into ``ground_truth_intents`` with stable ``gt_*`` ids."""
    return [
        {"id": f"gt_{i:03d}", "intent_description": x["intent"]}
        for i, x in enumerate(body, start=1)
    ]


def draft_intents_to_ground_truth_intents(body: list[dict[str, str]]) -> list[dict[str, str]]:
    """Same as :func:`parsed_intent_rows_to_ground_truth_intents` (alias for tests / imports)."""
    return parsed_intent_rows_to_ground_truth_intents(body)


@dataclass
class CollectConfig:
    images_dir: Path
    out_dir: Path
    model: str
    concurrency: int
    id_min: int | None
    id_max: int | None
    limit: int  # max screens after filter; 0 = no cap
    include_raw: bool


async def run_collect_async(cfg: CollectConfig) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pairs = list_images_by_id(cfg.images_dir)
    if not pairs:
        raise SystemExit(f"No images under {cfg.images_dir} (need names like 1.png).")

    filtered = [
        (eid, p)
        for eid, p in pairs
        if (cfg.id_min is None or eid >= cfg.id_min) and (cfg.id_max is None or eid <= cfg.id_max)
    ]
    if not filtered:
        raise SystemExit("No images in id range.")

    if cfg.limit > 0:
        filtered = filtered[: cfg.limit]
        logger.info("Processing first %d image(s) after filter (limit=%s).", len(filtered), cfg.limit)

    sem = asyncio.Semaphore(max(1, cfg.concurrency))
    created_utc = datetime.now(timezone.utc).isoformat()

    async def one(eid: int, image_path: Path) -> dict[str, Any]:
        async with sem:
            image_id_str = str(eid)
            raw, elapsed = await asyncio.to_thread(
                generate_baseline_gherkin_gemini_sync,
                str(image_path),
                cfg.model,
            )
            body, perr = parse_baseline_response_to_generated_intents(raw)
            gt_intents = parsed_intent_rows_to_ground_truth_intents(body)
            record = {
                "image_id": image_id_str,
                "source_image": str(image_path.resolve()),
                "pipeline": "baseline_gemini",
                "model": cfg.model,
                "llm_seconds": round(elapsed, 6),
                "parse_ok": perr is None and len(gt_intents) > 0,
                "parse_error": perr,
                "ground_truth_intents": gt_intents,
            }
            if cfg.include_raw or perr is not None or not gt_intents:
                record["baseline_raw_response"] = raw
            logger.info(
                "id=%s ground_truth_intents=%s parse_ok=%s",
                eid,
                len(gt_intents),
                record["parse_ok"],
            )
            return record

    try:
        screens = await asyncio.gather(*(one(eid, p) for eid, p in filtered))
    except KeyboardInterrupt:
        logger.warning("Interrupted; no bundle written.")
        sys.exit(130)

    screens_sorted = sorted(screens, key=lambda r: int(r["image_id"]) if str(r["image_id"]).isdigit() else r["image_id"])
    bundle = {
        "schema_version": "intent_coverage_judge_ground_truth_bundle_v1",
        "created_utc": created_utc,
        "images_dir": str(cfg.images_dir),
        "collect_model": cfg.model,
        "limit": cfg.limit,
        "screens": screens_sorted,
    }
    out_bundle = cfg.out_dir / GROUND_TRUTH_BUNDLE_FILENAME
    _atomic_write_json(out_bundle, bundle)
    logger.info("Done: wrote %s (%d screen(s))", out_bundle, len(screens_sorted))


def main() -> None:
    be = Path(__file__).resolve().parents[2]
    if str(be) not in sys.path:
        sys.path.insert(0, str(be))
    from dotenv import load_dotenv

    load_dotenv(be / ".env")
    load_dotenv()

    default_img = be / "data" / "images"
    default_data = be / "data"
    from experiments.intent_coverage_judge.run import (
        default_intent_coverage_judge_run_dir,
        default_timestamp,
    )

    ts = default_timestamp()
    default_out = default_intent_coverage_judge_run_dir(default_data, ts)

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--images-dir",
        type=Path,
        default=default_img,
        help=f"Screenshots with integer stem (default: {default_img})",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=f"Directory for {GROUND_TRUTH_BUNDLE_FILENAME} (default: {default_out})",
    )
    p.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash",
        help="Gemini model for baseline prompt (default: gemini-2.5-flash)",
    )
    p.add_argument("--concurrency", type=int, default=4, help="Max parallel Gemini calls (default: 4)")
    p.add_argument("--id-min", type=int, default=None)
    p.add_argument("--id-max", type=int, default=None)
    p.add_argument(
        "--limit",
        type=int,
        default=10,
        metavar="N",
        help="Max images to run after sort/filter (default: 10). Use 0 for all remaining.",
    )
    p.add_argument(
        "--include-raw",
        action="store_true",
        help="Include baseline_raw_response in each JSON (larger files)",
    )
    args = p.parse_args()
    if args.id_min is not None and args.id_max is not None and args.id_min > args.id_max:
        p.error("--id-min must be <= --id-max")
    if args.limit < 0:
        p.error("--limit must be >= 0 (0 means no limit)")

    out_dir = args.out_dir.resolve() if args.out_dir is not None else default_out

    cfg = CollectConfig(
        images_dir=args.images_dir.resolve(),
        out_dir=out_dir,
        model=args.model.strip(),
        concurrency=args.concurrency,
        id_min=args.id_min,
        id_max=args.id_max,
        limit=args.limit,
        include_raw=args.include_raw,
    )
    asyncio.run(run_collect_async(cfg))


__all__ = [
    "CollectConfig",
    "draft_intents_to_ground_truth_intents",
    "parse_baseline_response_to_generated_intents",
    "parsed_intent_rows_to_ground_truth_intents",
    "run_collect_async",
]


if __name__ == "__main__":
    main()
