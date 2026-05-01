import asyncio
import logging
from typing import Literal

from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.bdd_happy_path import BddHappyPathResult
from app.services.bdd_payload import parse_bdd_payload
from app.services.gemini_genai_client import default_generate_config, get_gemini_client, pil_image_to_part
from app.services.prompt_service import load_bdd_happy_path_prompt

logger = logging.getLogger(__name__)

BDD_HAPPY_PATH_MODEL = "gemini-2.5-flash"


def _resolve_generation_route(model: str | None) -> tuple[str, Literal["gemini", "openai"]]:
    effective = (model or BDD_HAPPY_PATH_MODEL).strip().lower()
    if effective.startswith("gpt-"):
        return effective, "openai"
    return effective, "gemini"


def _run_openai_bdd_sync(image_path: str, model_name: str) -> BddHappyPathResult:
    from app.services.openai_service import OpenAIService

    return OpenAIService(model_name).generate_bdd_happy_path(image_path)


def _run_gemini_bdd_sync(image_path: str, model_name: str = BDD_HAPPY_PATH_MODEL) -> BddHappyPathResult:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system_prompt = load_bdd_happy_path_prompt()
    client = get_gemini_client()
    try:
        img = Image.open(image_path)
    except Exception as exc:
        logger.error("Failed to open image: %s", exc)
        raise AIProcessingError(f"Failed to read image file: {exc}") from exc
    user_instruction = (
        "Analyze this UI screenshot and output the BDD JSON exactly as specified in the system instructions. "
        "Return ONLY the raw JSON."
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
        logger.error("Gemini BDD generation failed: %s", exc)
        raise AIProcessingError(f"BDD generation failed: {exc}") from exc
    content = response.text
    if not content:
        raise AIProcessingError("Received empty response from Gemini")
    logger.debug("BDD raw output length: %s", len(content))
    return parse_bdd_payload(content, result_model=model_name)


class BddHappyPathService:
    async def generate(
        self,
        image_path: str,
        model: str | None = None,
        backend: Literal["gemini", "openai"] | None = None,
    ) -> BddHappyPathResult:
        def _work() -> BddHappyPathResult:
            if backend is None:
                api_model, route = _resolve_generation_route(model)
                if route == "openai":
                    return _run_openai_bdd_sync(image_path, api_model)
                return _run_gemini_bdd_sync(image_path, api_model)
            if backend == "gemini":
                api_model = (model or BDD_HAPPY_PATH_MODEL).strip().lower()
                if not api_model:
                    api_model = BDD_HAPPY_PATH_MODEL
                return _run_gemini_bdd_sync(image_path, api_model)
            api_model = (model or "gpt-5").strip()
            if not api_model:
                api_model = "gpt-5"
            return _run_openai_bdd_sync(image_path, api_model)

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("BDD happy path service failed: %s", exc)
            raise AIProcessingError(f"BDD happy path service failed: {exc}") from exc


bdd_happy_path_service = BddHappyPathService()
