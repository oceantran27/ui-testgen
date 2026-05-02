"""Module 2: vision UI hierarchy (Agent 1) then text-only BDD (Agent 2)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.bdd_happy_path import BddHappyPathResult
from app.schemas.ui_hierarchy import UiHierarchyExtractionResult
from app.services.bdd_payload import parse_bdd_payload
from app.services.gemini_genai_client import default_generate_config, get_gemini_client, pil_image_to_part
from app.services.openai_service import OpenAIService
from app.services.prompt_service import load_bdd_bridge_stage1_prompt, load_bdd_bridge_stage2_prompt
from app.services.ui_hierarchy_payload import parse_ui_hierarchy_payload, ui_hierarchy_to_minified_json

logger = logging.getLogger(__name__)

BDD_TWO_STAGE_MODEL = "gemini-2.5-flash"


@dataclass(frozen=True)
class BddTwoStageRunResult:
    """Parsed Agent 1 hierarchy plus final BDD result (same objects used between stages)."""

    hierarchy: UiHierarchyExtractionResult
    bdd: BddHappyPathResult


def _resolve_generation_route(model: str | None) -> tuple[str, Literal["gemini", "openai"]]:
    effective = (model or BDD_TWO_STAGE_MODEL).strip().lower()
    if effective.startswith("gpt-"):
        return effective, "openai"
    return effective, "gemini"


def _run_openai_two_stage_sync(
    image_path: str, model_name: str
) -> tuple[UiHierarchyExtractionResult, BddHappyPathResult]:
    svc = OpenAIService(model_name)
    raw1 = svc.generate_bdd_bridge_stage1_raw(image_path)
    hierarchy = parse_ui_hierarchy_payload(raw1)
    payload = ui_hierarchy_to_minified_json(hierarchy)
    bdd = svc.generate_bdd_bridge_stage2_bdd(payload, result_model=model_name)
    return hierarchy, bdd


def _run_gemini_two_stage_sync(
    image_path: str, model_name: str = BDD_TWO_STAGE_MODEL
) -> tuple[UiHierarchyExtractionResult, BddHappyPathResult]:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system1 = load_bdd_bridge_stage1_prompt()
    system2 = load_bdd_bridge_stage2_prompt()
    client = get_gemini_client()
    try:
        img = Image.open(image_path)
    except Exception as exc:
        logger.error("Failed to open image: %s", exc)
        raise AIProcessingError(f"Failed to read image file: {exc}") from exc

    user1 = (
        "Analyze this UI screenshot and output the UI hierarchy JSON exactly as specified in the system instructions. "
        "Return ONLY the raw JSON."
    )
    try:
        response1 = client.models.generate_content(
            model=model_name,
            contents=[types.Part.from_text(text=user1), pil_image_to_part(img)],
            config=default_generate_config(system_instruction=system1),
        )
    except Exception as exc:
        logger.error("Gemini UI hierarchy (stage 1) failed: %s", exc)
        raise AIProcessingError(f"UI hierarchy extraction failed: {exc}") from exc
    raw1 = response1.text
    if not raw1:
        raise AIProcessingError("Received empty response from Gemini (stage 1)")
    hierarchy = parse_ui_hierarchy_payload(raw1)
    payload = ui_hierarchy_to_minified_json(hierarchy)

    user2 = (
        "UI hierarchy JSON from Agent 1 (sole source of truth for visible UI wording):\n"
        f"{payload}\n\n"
        "Produce the BDD happy-path JSON per the system instructions. Return ONLY the raw JSON."
    )
    try:
        response2 = client.models.generate_content(
            model=model_name,
            contents=[types.Part.from_text(text=user2)],
            config=default_generate_config(system_instruction=system2),
        )
    except Exception as exc:
        logger.error("Gemini BDD (stage 2) failed: %s", exc)
        raise AIProcessingError(f"BDD generation failed: {exc}") from exc
    raw2 = response2.text
    if not raw2:
        raise AIProcessingError("Received empty response from Gemini (stage 2)")
    bdd = parse_bdd_payload(raw2, result_model=model_name)
    return hierarchy, bdd


def _run_two_stage_sync(
    image_path: str,
    model: str | None,
    backend: Literal["gemini", "openai"] | None,
) -> BddTwoStageRunResult:
    if backend is None:
        api_model, route = _resolve_generation_route(model)
        if route == "openai":
            h, b = _run_openai_two_stage_sync(image_path, api_model)
        else:
            h, b = _run_gemini_two_stage_sync(image_path, api_model)
        return BddTwoStageRunResult(hierarchy=h, bdd=b)
    if backend == "gemini":
        api_model = (model or BDD_TWO_STAGE_MODEL).strip().lower() or BDD_TWO_STAGE_MODEL
        h, b = _run_gemini_two_stage_sync(image_path, api_model)
        return BddTwoStageRunResult(hierarchy=h, bdd=b)
    api_model = (model or "gpt-5").strip() or "gpt-5"
    h, b = _run_openai_two_stage_sync(image_path, api_model)
    return BddTwoStageRunResult(hierarchy=h, bdd=b)


class BddTwoStageService:
    async def generate(
        self,
        image_path: str,
        model: str | None = None,
        backend: Literal["gemini", "openai"] | None = None,
    ) -> BddHappyPathResult:
        def _work() -> BddHappyPathResult:
            return _run_two_stage_sync(image_path, model, backend).bdd

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("BDD two-stage service failed: %s", exc)
            raise AIProcessingError(f"BDD two-stage service failed: {exc}") from exc

    async def generate_with_hierarchy(
        self,
        image_path: str,
        model: str | None = None,
        backend: Literal["gemini", "openai"] | None = None,
    ) -> BddTwoStageRunResult:
        def _work() -> BddTwoStageRunResult:
            return _run_two_stage_sync(image_path, model, backend)

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("BDD two-stage service failed: %s", exc)
            raise AIProcessingError(f"BDD two-stage service failed: {exc}") from exc


bdd_two_stage_service = BddTwoStageService()
