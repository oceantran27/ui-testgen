from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.bdd_happy_path import BddHappyPathResult
from app.schemas.ui_hierarchy import UIHierarchyResult
from app.services.bdd_payload import parse_bdd_payload
from app.services.gemini_genai_client import default_generate_config, get_gemini_client, pil_image_to_part
from app.services.prompt_service import load_bdd_bridge_stage1_prompt, load_bdd_bridge_stage2_prompt
from app.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Module2Bundle:
    """Agent 1 UI hierarchy (parsed JSON object) + Agent 2 BDD + per-stage wall times."""

    bdd: BddHappyPathResult
    hierarchy: dict[str, Any]
    stage1_llm_seconds: float
    stage2_llm_seconds: float


def _run_gemini_stage1(image_path: str, model_name: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system_prompt = load_bdd_bridge_stage1_prompt()
    client = get_gemini_client()
    try:
        img = Image.open(image_path)
    except Exception as exc:
        logger.error("Failed to open image: %s", exc)
        raise AIProcessingError(f"Failed to read image file: {exc}") from exc
    user_instruction = (
        "Analyze this UI screenshot and output the UI hierarchy JSON (Agent 1) exactly as specified. "
        "Return exactly one valid JSON object. Do not include markdown, code fences, or extra text."
    )
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_text(text=user_instruction),
                pil_image_to_part(img),
            ],
            config=default_generate_config(system_instruction=system_prompt),
        )
    except Exception as exc:
        logger.error("Gemini Stage 1 extraction failed: %s", exc)
        raise AIProcessingError(f"Stage 1 extraction failed: {exc}") from exc
    content = response.text
    if not content:
        raise AIProcessingError("Received empty response from Gemini (Stage 1)")
    return content


def _run_gemini_stage2(extraction_json: str, model_name: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system_prompt = load_bdd_bridge_stage2_prompt()
    client = get_gemini_client()
    user_text = (
        "UI hierarchy JSON from Agent 1 (sole source of truth for visible UI wording):\n"
        f"{extraction_json}\n\n"
        "Produce the BDD happy-path JSON per the system instructions. Return exactly one JSON object. "
        "Do not include markdown, code fences, or extra text."
    )
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=user_text,
            config=default_generate_config(system_instruction=system_prompt),
        )
    except Exception as exc:
        logger.error("Gemini Stage 2 generation failed: %s", exc)
        raise AIProcessingError(f"Stage 2 generation failed: {exc}") from exc
    content = response.text
    if not content:
        raise AIProcessingError("Received empty response from Gemini (Stage 2)")
    return content


def _extract_stage1(
    image_path: str,
    stage1_model: str,
) -> tuple[str, float]:
    t0 = time.perf_counter()
    logger.info("Starting Module 2 Stage 1 (UI Extraction) with model %s", stage1_model)
    if stage1_model.startswith("gpt-"):
        raw = OpenAIService(stage1_model).generate_bdd_bridge_stage1_raw(image_path)
    else:
        raw = _run_gemini_stage1(image_path, stage1_model)
    elapsed = time.perf_counter() - t0
    logger.info("Module 2 Stage 1 completed. Output length: %d", len(raw))
    return raw, elapsed


def _run_stage2_to_bdd(ui_hierarchy_json: str, stage2_model: str) -> BddHappyPathResult:
    logger.info("Starting Module 2 Stage 2 (BDD Generation) with model %s", stage2_model)
    if stage2_model.startswith("gpt-"):
        return OpenAIService(stage2_model).generate_bdd_bridge_stage2_bdd(
            ui_hierarchy_json, result_model=stage2_model
        )
    bdd_json_str = _run_gemini_stage2(ui_hierarchy_json, stage2_model)
    return parse_bdd_payload(bdd_json_str, result_model=stage2_model)


def _run_module2_sync(
    image_path: str,
    stage1_model: str,
    stage2_model: str,
) -> Module2Bundle:
    ui_hierarchy_json, stage1_seconds = _extract_stage1(image_path, stage1_model)
    try:
        hierarchy_obj = json.loads(ui_hierarchy_json)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Agent 1 returned invalid JSON: {exc}") from exc
    if not isinstance(hierarchy_obj, dict):
        raise AIProcessingError("Agent 1 JSON root must be an object")
    try:
        UIHierarchyResult.model_validate(hierarchy_obj)
    except ValidationError as exc:
        raise AIProcessingError(
            f"Agent 1 UI hierarchy failed ui-hierarchy-v2 validation: {exc}"
        ) from exc
    t_stage2 = time.perf_counter()
    bdd = _run_stage2_to_bdd(ui_hierarchy_json, stage2_model)
    stage2_seconds = time.perf_counter() - t_stage2

    return Module2Bundle(
        bdd=bdd,
        hierarchy=hierarchy_obj,
        stage1_llm_seconds=stage1_seconds,
        stage2_llm_seconds=stage2_seconds,
    )


class Module2PipelineService:
    async def generate_with_hierarchy(
        self,
        image_path: str,
        *,
        stage1_model: str | None = None,
        stage2_model: str | None = None,
    ) -> Module2Bundle:
        s1 = (stage1_model or settings.BDD_TWO_STAGE_STAGE1_MODEL).strip().lower()
        s2 = (stage2_model or settings.BDD_TWO_STAGE_STAGE2_MODEL).strip().lower()

        def _work() -> Module2Bundle:
            return _run_module2_sync(image_path, s1, s2)

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("Module 2 Pipeline failed: %s", exc)
            raise AIProcessingError(f"Module 2 Pipeline failed: {exc}") from exc

    async def generate_bdd(
        self,
        image_path: str,
        stage1_model: str | None = None,
        stage2_model: str | None = None,
    ) -> BddHappyPathResult:
        bundle = await self.generate_with_hierarchy(
            image_path,
            stage1_model=stage1_model,
            stage2_model=stage2_model,
        )
        return bundle.bdd


module_2_pipeline_service = Module2PipelineService()
