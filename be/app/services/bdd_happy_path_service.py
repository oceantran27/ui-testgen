import asyncio
import json
import logging
from functools import lru_cache
from pathlib import Path

import google.generativeai as genai
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.bdd_happy_path import BddFeatureBlock, BddHappyPathResult, BddScenarioItem

logger = logging.getLogger(__name__)

BDD_HAPPY_PATH_MODEL = "gemini-2.5-flash"


def _resolve_prompt_path() -> Path:
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / settings.BDD_HAPPY_PATH_PROMPT_PATH


@lru_cache(maxsize=1)
def _load_bdd_happy_path_prompt() -> str:
    resolved = _resolve_prompt_path()
    try:
        return resolved.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to load BDD happy path prompt from %s: %s", resolved, exc)
        raise AIProcessingError(f"Failed to load BDD happy path prompt: {exc}")


def _build_combined_gherkin(feature: BddFeatureBlock, scenarios: list[BddScenarioItem]) -> str:
    lines: list[str] = [
        f"Feature: {feature.name}",
    ]
    if feature.description.strip():
        lines.append(feature.description.strip())
    lines.append("")
    for sc in scenarios:
        lines.append(sc.gherkin.strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _parse_bdd_payload(raw: str) -> BddHappyPathResult:
    minified = extract_and_minify_json(raw)
    if not minified:
        raise AIProcessingError("Could not parse BDD JSON from model output")
    try:
        data = json.loads(minified)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Invalid BDD JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIProcessingError("BDD output must be a JSON object")
    feature_raw = data.get("feature") or data.get("Feature")
    if not isinstance(feature_raw, dict):
        raise AIProcessingError("BDD output must include object 'feature'")
    scenarios_data = data.get("scenarios") or data.get("Scenarios")
    try:
        feature = BddFeatureBlock.model_validate(feature_raw)
        if not isinstance(scenarios_data, list) or not scenarios_data:
            raise ValueError("scenarios must be a non-empty array")
        scenarios = [BddScenarioItem.model_validate(s) for s in scenarios_data]
    except Exception as exc:
        raise AIProcessingError(f"Invalid BDD payload shape: {exc}") from exc

    return BddHappyPathResult(
        model=BDD_HAPPY_PATH_MODEL,
        feature=feature,
        scenarios=scenarios,
        combined_gherkin=_build_combined_gherkin(feature, scenarios),
    )


def _run_gemini_bdd_sync(image_path: str) -> BddHappyPathResult:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system_prompt = _load_bdd_happy_path_prompt()
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        BDD_HAPPY_PATH_MODEL,
        generation_config={"temperature": 0.0},
    )
    try:
        img = Image.open(image_path)
    except Exception as exc:
        logger.error("Failed to open image: %s", exc)
        raise AIProcessingError(f"Failed to read image file: {exc}") from exc
    user_instruction = (
        "You are given a single viewport screenshot of a Web UI. "
        "Using the system instructions, produce the required JSON only: "
        "feature plus scenarios (happy path, Gherkin in each gherkin field). "
        "Do not add markdown, explanations, or text outside the JSON object."
    )
    try:
        response = model.generate_content([system_prompt, user_instruction, img])
    except Exception as exc:
        logger.error("Gemini BDD generation failed: %s", exc)
        raise AIProcessingError(f"BDD generation failed: {exc}") from exc
    content = response.text
    if not content:
        raise AIProcessingError("Received empty response from Gemini")
    logger.debug("BDD raw output length: %s", len(content))
    return _parse_bdd_payload(content)


class BddHappyPathService:
    async def generate(self, image_path: str) -> BddHappyPathResult:
        def _work() -> BddHappyPathResult:
            return _run_gemini_bdd_sync(image_path)

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("BDD happy path service failed: %s", exc)
            raise AIProcessingError(f"BDD happy path service failed: {exc}") from exc


bdd_happy_path_service = BddHappyPathService()
