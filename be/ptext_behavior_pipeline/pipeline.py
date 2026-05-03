"""Orchestrate Stage B → C per capture, then Stage A on the text bundle."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from app.core.exceptions import AIProcessingError
from app.services.ui_hierarchy_payload import parse_ui_hierarchy_payload, ui_hierarchy_to_minified_json

from ptext_behavior_pipeline.bundle_builder import minified_captures_bundle
from ptext_behavior_pipeline.llm import PtextOpenAIClient
from ptext_behavior_pipeline.parsing import parse_bdd_bundle_ptext, parse_behavior_flow_stage_a
from ptext_behavior_pipeline.schemas import PtextPipelineResult

_CAPTURE_RE = re.compile(r"^img_(\d{3})$")


def _validate_inputs(captures: list[tuple[str, str]]) -> None:
    if not captures:
        raise AIProcessingError("captures must be non-empty")
    seen: set[str] = set()
    for cap_id, img_path in captures:
        if cap_id in seen:
            raise AIProcessingError(f"duplicate capture_id: {cap_id!r}")
        seen.add(cap_id)
        if _CAPTURE_RE.match(cap_id) is None:
            raise AIProcessingError(f"capture_id must match img_### (e.g. img_001): {cap_id!r}")
        p = Path(img_path)
        if not p.is_file():
            raise AIProcessingError(f"Image not found for {cap_id}: {img_path}")


def _run_bc_sync(client: PtextOpenAIClient, capture_id: str, image_path: str) -> dict[str, Any]:
    raw_b = client.stage_b_vision_raw(image_path)
    hierarchy = parse_ui_hierarchy_payload(raw_b)
    mini = ui_hierarchy_to_minified_json(hierarchy)
    raw_c = client.stage_c_text_raw(mini)
    bdd = parse_bdd_bundle_ptext(raw_c)
    return {
        "capture_id": capture_id,
        "hierarchy": hierarchy.model_dump(mode="json"),
        "bdd_bundle": bdd.model_dump(mode="json"),
    }


async def run_ptext_pipeline_async(
    captures: list[tuple[str, str]],
    *,
    model: str | None = None,
    max_concurrency: int = 4,
) -> PtextPipelineResult:
    """Run B+C with bounded concurrency; then A once."""
    _validate_inputs(captures)
    client = PtextOpenAIClient(model=model)
    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _wrapped(cid: str, path: str) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(_run_bc_sync, client, cid, path)

    entries = await asyncio.gather(*(_wrapped(cid, pth) for cid, pth in captures))
    bundle = minified_captures_bundle(list(entries))
    raw_a = await asyncio.to_thread(client.stage_a_text_raw, bundle)
    expected = [cid for cid, _ in captures]
    flows = parse_behavior_flow_stage_a(raw_a, expected_ids=expected)
    return PtextPipelineResult(
        model=client.model,
        flows=flows,
        captures=list(entries),
    )


def run_ptext_pipeline(
    captures: list[tuple[str, str]],
    *,
    model: str | None = None,
    max_concurrency: int = 4,
) -> PtextPipelineResult:
    """Blocking entry suitable for CLI and scripts."""
    return asyncio.run(
        run_ptext_pipeline_async(captures, model=model, max_concurrency=max_concurrency)
    )
