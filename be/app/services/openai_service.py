import base64
import logging
from functools import cached_property
from pathlib import Path

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.bdd_happy_path import BddHappyPathResult
from app.services.bdd_payload import parse_bdd_payload
from app.services.prompt_service import (
    load_bdd_bridge_stage1_prompt,
    load_bdd_bridge_stage2_prompt,
    load_bdd_happy_path_prompt,
    load_system_prompt,
)

logger = logging.getLogger(__name__)

_MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
}


def _mime_type_for_path(image_path: str) -> str:
    ext = Path(image_path).suffix.lower().lstrip(".")
    return _MIME_BY_EXT.get(ext, "image/jpeg")


class OpenAIService:
    """OpenAI client. Vision-extractor prompt (legacy ``analyze_image``) loads lazily-only when needed.

    BDD / bridge methods load their own prompts (e.g. ``load_bdd_bridge_stage2_prompt``).
    """

    def __init__(self, model_name: str = "gpt-4.1"):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model_name

    @cached_property
    def _vision_extractor_system_prompt(self) -> str:
        return load_system_prompt()

    def _encode_image(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            logger.error("Failed to encode image: %s", e)
            raise AIProcessingError(f"Failed to read image file: {str(e)}") from e

    def analyze_image(self, image_path: str) -> str:
        base64_image = self._encode_image(image_path)
        mime_type = _mime_type_for_path(image_path)

        try:
            logger.info("Sending request to OpenAI for image: %s", image_path)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._vision_extractor_system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this web UI screenshot using the system instructions and return exactly one valid JSON object "
                                    "that follows the required schema with page_overview, scenarios, and business_rules_and_constraints. "
                                    "Do not return markdown, code fences, or extra text."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content

            logger.info("--- RAW LLM OUTPUT START ---")
            logger.info(content)
            logger.info("--- RAW LLM OUTPUT END ---")

            if not content:
                raise AIProcessingError("Received empty response from OpenAI")

            return content

        except AIProcessingError:
            raise
        except Exception as e:
            logger.error("OpenAI API connection failed or processing error: %s", e)
            raise AIProcessingError(f"AI Processing failed: {str(e)}") from e

    def generate_bdd_happy_path(self, image_path: str) -> BddHappyPathResult:
        if not settings.OPENAI_API_KEY:
            raise AIProcessingError("OPENAI_API_KEY is not configured")
        system_prompt = load_bdd_happy_path_prompt()
        base64_image = self._encode_image(image_path)
        mime_type = _mime_type_for_path(image_path)
        user_text = (
            "Analyze this UI screenshot and output the BDD JSON exactly as specified in the system instructions. "
            "Return exactly one JSON object with the required shape (feature and scenarios). "
            "Do not include markdown, code fences, or extra text."
        )
        try:
            logger.info("Sending OpenAI BDD request for image: %s model=%s", image_path, self.model)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.error("OpenAI BDD generation failed: %s", exc)
            raise AIProcessingError(f"BDD generation failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise AIProcessingError("Received empty response from OpenAI")
        logger.debug("BDD raw output length (OpenAI): %s", len(content))
        return parse_bdd_payload(content, result_model=self.model)

    def generate_bdd_bridge_stage1_raw(self, image_path: str) -> str:
        if not settings.OPENAI_API_KEY:
            raise AIProcessingError("OPENAI_API_KEY is not configured")
        system_prompt = load_bdd_bridge_stage1_prompt()
        base64_image = self._encode_image(image_path)
        mime_type = _mime_type_for_path(image_path)
        user_text = (
            "Analyze this UI screenshot and output the UI hierarchy JSON (Agent 1) exactly as specified. "
            "Return exactly one JSON object. Do not include markdown, code fences, or extra text."
        )
        try:
            logger.info(
                "Sending OpenAI BDD bridge stage1 request for image: %s model=%s",
                image_path,
                self.model,
            )
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.error("OpenAI BDD bridge stage1 failed: %s", exc)
            raise AIProcessingError(f"BDD bridge stage1 failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise AIProcessingError("Received empty response from OpenAI (bridge stage1)")
        logger.debug("BDD bridge stage1 raw output length (OpenAI): %s", len(content))
        return content

    def generate_bdd_bridge_stage2_bdd(self, extraction_json: str, *, result_model: str) -> BddHappyPathResult:
        if not settings.OPENAI_API_KEY:
            raise AIProcessingError("OPENAI_API_KEY is not configured")
        system_prompt = load_bdd_bridge_stage2_prompt()
        user_text = (
            "UI hierarchy JSON from Agent 1 (sole source of truth for visible UI wording):\n"
            f"{extraction_json}\n\n"
            "Produce the BDD happy-path JSON per the system instructions. Return exactly one JSON object. "
            "Do not include markdown, code fences, or extra text."
        )
        try:
            logger.info("Sending OpenAI BDD bridge stage2 request model=%s", self.model)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.error("OpenAI BDD bridge stage2 failed: %s", exc)
            raise AIProcessingError(f"BDD bridge stage2 failed: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise AIProcessingError("Received empty response from OpenAI (bridge stage2)")
        logger.debug("BDD bridge stage2 raw output length (OpenAI): %s", len(content))
        return parse_bdd_payload(content, result_model=result_model)
