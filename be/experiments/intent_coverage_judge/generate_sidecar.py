"""Generate ``GeneratedScreenFile`` payloads for intent_coverage_judge (baseline vs propose)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from app.services.baseline_gherkin_coverage_service import generate_baseline_gherkin_gemini_sync
from app.services.ui_extraction_payload import filter_scoped_ui_extraction, user_intent_input_to_minified_json
from app.services.ui_extraction_service import extract_ui_extraction_gemini_sync
from app.services.user_intent_service import generate_user_intents_openai_sync

from experiments.intent_coverage_judge.collect_baseline import parse_baseline_response_to_generated_intents
from experiments.intent_coverage_judge.schemas import GeneratedIntent, GeneratedScreenFile, GroundTruthScreenFile
from experiments.test_scenario_title_eval.images import list_images_by_id

_IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]


def resolve_image_for_id(images_dir: Path, image_id: str) -> Path | None:
    """
    Locate the image for this ``image_id``, matching :func:`list_images_by_id` rules.

    Numeric ``image_id`` (e.g. ``"1"``) resolves to any file whose stem is digits with the same
    integer value (``1.png``, ``01.png``, ``001.png``).
    Non-numeric ids fall back to a literal ``{image_id}.{ext}`` lookup.
    """
    if not images_dir.is_dir():
        return None
    stem = str(Path(str(image_id).strip()).name)
    try:
        want = int(stem)
    except ValueError:
        want = None
    if want is not None:
        for eid, path in list_images_by_id(images_dir):
            if eid == want:
                return path
        return None
    for ext in _IMAGE_EXTS:
        p = images_dir / f"{stem}{ext}"
        if p.is_file():
            return p
        p_ci = images_dir / f"{stem}{ext.upper()}"
        if p_ci.is_file():
            return p_ci
    return None

def baseline_response_to_generated_screen(image_id: str, raw: str) -> GeneratedScreenFile:
    body, _perr = parse_baseline_response_to_generated_intents(raw)
    intents = [
        GeneratedIntent(id=f"gen_{i:03d}", intent=x["intent"], gherkin=x.get("gherkin", ""))
        for i, x in enumerate(body, start=1)
    ]
    return GeneratedScreenFile(image_id=image_id, generated_intents=intents)


def generated_screen_baseline_sync(image_path: Path, image_id: str, gemini_model: str) -> GeneratedScreenFile:
    raw, _sec = generate_baseline_gherkin_gemini_sync(str(image_path), gemini_model)
    return baseline_response_to_generated_screen(image_id, raw)


def user_intents_payload_to_generated_screen(
    image_id: str,
    payload: dict,
) -> GeneratedScreenFile:
    rows = payload.get("user_intents")
    if not isinstance(rows, list):
        rows = []
    intents: list[GeneratedIntent] = []
    for i, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        intent = item.get("intent")
        gherkin = item.get("gherkin") if isinstance(item.get("gherkin"), str) else ""
        if not isinstance(intent, str) or not intent.strip():
            continue
        intents.append(
            GeneratedIntent(id=f"gen_{i:03d}", intent=intent.strip(), gherkin=gherkin.strip()),
        )
    return GeneratedScreenFile(image_id=image_id, generated_intents=intents)


def generated_screen_propose_sync(
    image_path: Path,
    image_id: str,
    gemini_model: str,
    openai_model: str,
) -> GeneratedScreenFile:
    ui_full, _s1 = extract_ui_extraction_gemini_sync(str(image_path), gemini_model)
    scoped = filter_scoped_ui_extraction(ui_full)
    minified = user_intent_input_to_minified_json(scoped)
    intents_obj = generate_user_intents_openai_sync(image_id, minified, openai_model)
    payload = intents_obj.model_dump(mode="json")
    return user_intents_payload_to_generated_screen(image_id, payload)


async def generate_for_judge_async(
    gt_by_id: dict[str, GroundTruthScreenFile],
    images_dir: Path,
    *,
    mode: Literal["baseline", "propose"],
    baseline_model: str,
    stage1_model: str,
    stage2_model: str,
    concurrency: int,
) -> dict[str, GeneratedScreenFile]:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(iid: str) -> tuple[str, GeneratedScreenFile]:
        img = resolve_image_for_id(images_dir, iid)
        if img is None:
            raise FileNotFoundError(f"No image for image_id={iid!r} under {images_dir}")
        async with sem:
            def _baseline() -> GeneratedScreenFile:
                return generated_screen_baseline_sync(img, iid, baseline_model)

            def _propose() -> GeneratedScreenFile:
                return generated_screen_propose_sync(img, iid, stage1_model, stage2_model)

            if mode == "baseline":
                row = await asyncio.to_thread(_baseline)
            else:
                row = await asyncio.to_thread(_propose)
            return iid, row

    pairs = await asyncio.gather(*(one(iid) for iid in sorted(gt_by_id.keys())))
    return {k: v for k, v in pairs}


__all__ = [
    "baseline_response_to_generated_screen",
    "generated_screen_baseline_sync",
    "generated_screen_propose_sync",
    "generate_for_judge_async",
    "resolve_image_for_id",
    "user_intents_payload_to_generated_screen",
]
