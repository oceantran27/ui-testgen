"""Two-stage pipeline: vision UI hierarchy (stage 1), then text-only test scenario suite (stage 2)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Literal

from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.test_scenario_generation import TestScenarioSuite
from app.schemas.ui_hierarchy import UIHierarchyResult
from app.services.gemini_genai_client import default_generate_config, get_gemini_client, pil_image_to_part
from app.services.openai_service import OpenAIService
from app.services.prompt_service import load_two_stage_test_scenario_prompt, load_two_stage_ui_hierarchy_prompt
from app.services.test_scenario_payload import parse_test_scenario_suite_payload
from app.services.ui_hierarchy_payload import parse_ui_hierarchy_payload, ui_hierarchy_to_minified_json

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TwoStageTestScenarioRunResult:
    """Parsed stage-1 hierarchy plus final test scenario suite (same objects between stages)."""

    hierarchy: UIHierarchyResult
    suite: TestScenarioSuite
    stage1_llm_seconds: float = 0.0
    stage2_llm_seconds: float = 0.0


def _looks_like_openai_model_id(model_id: str) -> bool:
    return model_id.strip().lower().startswith("gpt-")


def _extract_hierarchy_gemini_sync(image_path: str, gemini_model: str) -> UIHierarchyResult:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system1 = load_two_stage_ui_hierarchy_prompt()
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
            model=gemini_model,
            contents=[types.Part.from_text(text=user1), pil_image_to_part(img)],
            config=default_generate_config(system_instruction=system1),
        )
    except Exception as exc:
        logger.error("Gemini UI hierarchy (stage 1) failed: %s", exc)
        raise AIProcessingError(f"UI hierarchy extraction failed: {exc}") from exc
    raw1 = response1.text
    if not raw1:
        raise AIProcessingError("Received empty response from Gemini (stage 1)")
    return parse_ui_hierarchy_payload(raw1)


def _generate_suite_via_gemini_text_sync(minified_payload: str, gemini_model: str) -> TestScenarioSuite:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system2 = load_two_stage_test_scenario_prompt()
    client = get_gemini_client()
    user2 = (
        "UI hierarchy JSON from stage 1 (sole source of truth for visible UI wording):\n"
        f"{minified_payload}\n\n"
        "Produce the test scenario suite JSON per the system instructions. Return ONLY the raw JSON."
    )
    try:
        response2 = client.models.generate_content(
            model=gemini_model,
            contents=[types.Part.from_text(text=user2)],
            config=default_generate_config(system_instruction=system2),
        )
    except Exception as exc:
        logger.error("Gemini stage 2 test scenario generation failed: %s", exc)
        raise AIProcessingError(f"Test scenario generation failed: {exc}") from exc
    raw2 = response2.text
    if not raw2:
        raise AIProcessingError("Received empty response from Gemini (stage 2)")
    return parse_test_scenario_suite_payload(raw2, result_model=gemini_model)


def _generate_suite_via_openai_stage2_sync(minified_payload: str, openai_model: str) -> TestScenarioSuite:
    return OpenAIService(openai_model).generate_two_stage_test_scenarios_from_hierarchy(
        minified_payload, result_model=openai_model
    )


def _run_gemini_both_stages_sync(
    image_path: str, gemini_model: str
) -> TwoStageTestScenarioRunResult:
    t0 = time.perf_counter()
    hierarchy = _extract_hierarchy_gemini_sync(image_path, gemini_model)
    t1 = time.perf_counter()
    payload = ui_hierarchy_to_minified_json(hierarchy)
    t2 = time.perf_counter()
    suite = _generate_suite_via_gemini_text_sync(payload, gemini_model)
    t3 = time.perf_counter()
    return TwoStageTestScenarioRunResult(
        hierarchy=hierarchy,
        suite=suite,
        stage1_llm_seconds=t1 - t0,
        stage2_llm_seconds=t3 - t2,
    )


def _run_hybrid_gemini_openai_sync(
    image_path: str, gemini_stage1: str, openai_stage2: str
) -> TwoStageTestScenarioRunResult:
    if _looks_like_openai_model_id(gemini_stage1):
        raise AIProcessingError(
            "Hybrid pipeline expects a Gemini model for stage 1 (UI extraction). "
            "Use backend='openai' for an all-OpenAI two-stage pipeline, or fix TWO_STAGE_STAGE1_MODEL / stage1_model."
        )
    if not settings.OPENAI_API_KEY:
        raise AIProcessingError(
            "OPENAI_API_KEY is not configured (required for GPT stage 2 in hybrid pipeline)"
        )
    t0 = time.perf_counter()
    hierarchy = _extract_hierarchy_gemini_sync(image_path, gemini_stage1)
    t1 = time.perf_counter()
    payload = ui_hierarchy_to_minified_json(hierarchy)
    t2 = time.perf_counter()
    suite = _generate_suite_via_openai_stage2_sync(payload, openai_stage2)
    t3 = time.perf_counter()
    return TwoStageTestScenarioRunResult(
        hierarchy=hierarchy,
        suite=suite,
        stage1_llm_seconds=t1 - t0,
        stage2_llm_seconds=t3 - t2,
    )


def _run_openai_two_stage_sync(
    image_path: str, model_name: str
) -> TwoStageTestScenarioRunResult:
    svc = OpenAIService(model_name)
    t0 = time.perf_counter()
    raw1 = svc.generate_two_stage_ui_hierarchy_raw(image_path)
    hierarchy = parse_ui_hierarchy_payload(raw1)
    t1 = time.perf_counter()
    payload = ui_hierarchy_to_minified_json(hierarchy)
    t2 = time.perf_counter()
    suite = svc.generate_two_stage_test_scenarios_from_hierarchy(payload, result_model=model_name)
    t3 = time.perf_counter()
    return TwoStageTestScenarioRunResult(
        hierarchy=hierarchy,
        suite=suite,
        stage1_llm_seconds=t1 - t0,
        stage2_llm_seconds=t3 - t2,
    )


def _legacy_single_model_route(model: str) -> tuple[str, Literal["gemini", "openai"]]:
    api_model = model.strip().lower()
    if _looks_like_openai_model_id(api_model):
        return api_model, "openai"
    return api_model, "gemini"


def _run_two_stage_sync(
    image_path: str,
    model: str | None,
    backend: Literal["gemini", "openai"] | None,
    stage1_model: str | None,
    stage2_model: str | None,
) -> TwoStageTestScenarioRunResult:
    if backend == "gemini":
        uni = (model or stage1_model or stage2_model or settings.TWO_STAGE_STAGE1_MODEL).strip()
        if not uni:
            uni = "gemini-2.5-flash"
        logger.info("two-stage pipeline=all_gemini stage1=%s stage2=%s", uni, uni)
        return _run_gemini_both_stages_sync(image_path, uni)
    if backend == "openai":
        uni = (model or stage1_model or stage2_model or settings.TWO_STAGE_STAGE2_MODEL).strip()
        if not uni:
            uni = "gpt-5"
        logger.info("two-stage pipeline=all_openai model=%s", uni)
        return _run_openai_two_stage_sync(image_path, uni)

    stage_explicit = stage1_model is not None or stage2_model is not None
    if stage_explicit:
        r1 = (stage1_model or settings.TWO_STAGE_STAGE1_MODEL).strip()
        r2 = (stage2_model or settings.TWO_STAGE_STAGE2_MODEL).strip()

        if _looks_like_openai_model_id(r1) and _looks_like_openai_model_id(r2):
            uni = r1 if stage1_model is not None else r2
            logger.info("two-stage pipeline=all_openai model=%s (stage overrides)", uni)
            return _run_openai_two_stage_sync(image_path, uni)

        if _looks_like_openai_model_id(r2):
            logger.info("two-stage pipeline=hybrid stage1=%s stage2=%s", r1, r2)
            return _run_hybrid_gemini_openai_sync(image_path, r1, r2)

        if _looks_like_openai_model_id(r1):
            raise AIProcessingError(
                "When stage 2 uses Gemini, stage 1 must be a Gemini-capable vision model ID, not GPT. "
                "Omit stage1_model to use settings.TWO_STAGE_STAGE1_MODEL, or fix stage1_model."
            )
        logger.info("two-stage pipeline=dual_gemini stage1=%s stage2=%s", r1, r2)
        t0 = time.perf_counter()
        h = _extract_hierarchy_gemini_sync(image_path, r1)
        t1 = time.perf_counter()
        payload = ui_hierarchy_to_minified_json(h)
        t2 = time.perf_counter()
        b = _generate_suite_via_gemini_text_sync(payload, r2)
        t3 = time.perf_counter()
        return TwoStageTestScenarioRunResult(
            hierarchy=h,
            suite=b,
            stage1_llm_seconds=t1 - t0,
            stage2_llm_seconds=t3 - t2,
        )

    if model:
        ml = model.strip()
        if ml:
            api_model, route = _legacy_single_model_route(ml)
            if route == "openai":
                logger.info("two-stage pipeline=all_openai model=%s", api_model)
                return _run_openai_two_stage_sync(image_path, api_model)
            logger.info("two-stage pipeline=all_gemini model=%s", api_model)
            return _run_gemini_both_stages_sync(image_path, api_model)

    r1 = settings.TWO_STAGE_STAGE1_MODEL
    r2 = settings.TWO_STAGE_STAGE2_MODEL
    logger.info("two-stage pipeline=hybrid_defaults stage1=%s stage2=%s", r1, r2)
    return _run_hybrid_gemini_openai_sync(image_path, r1, r2)


class TwoStageTestScenarioService:
    async def generate(
        self,
        image_path: str,
        model: str | None = None,
        backend: Literal["gemini", "openai"] | None = None,
        *,
        stage1_model: str | None = None,
        stage2_model: str | None = None,
    ) -> TestScenarioSuite:
        def _work() -> TestScenarioSuite:
            return _run_two_stage_sync(image_path, model, backend, stage1_model, stage2_model).suite

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("Two-stage test scenario service failed: %s", exc)
            raise AIProcessingError(f"Two-stage test scenario service failed: {exc}") from exc

    async def generate_with_hierarchy(
        self,
        image_path: str,
        model: str | None = None,
        backend: Literal["gemini", "openai"] | None = None,
        *,
        stage1_model: str | None = None,
        stage2_model: str | None = None,
    ) -> TwoStageTestScenarioRunResult:
        def _work() -> TwoStageTestScenarioRunResult:
            return _run_two_stage_sync(image_path, model, backend, stage1_model, stage2_model)

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("Two-stage test scenario service failed: %s", exc)
            raise AIProcessingError(f"Two-stage test scenario service failed: {exc}") from exc


two_stage_test_scenario_service = TwoStageTestScenarioService()
