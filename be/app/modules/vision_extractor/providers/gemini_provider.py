import logging

from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.providers.base_provider import BaseVisionProvider
from app.services.gemini_genai_client import default_generate_config, get_gemini_client, pil_image_to_part

logger = logging.getLogger(__name__)


class GeminiVisionProvider(BaseVisionProvider):
    def __init__(self, system_prompt: str, model_name: str = "gemini-2.5-flash"):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured in settings")

        self._client = get_gemini_client()
        self.model_name = model_name
        self.system_prompt = system_prompt

    def analyze_image(self, image_path: str) -> str:
        try:
            img = Image.open(image_path)
        except Exception as exc:
            logger.error("Failed to open image: %s", exc)
            raise AIProcessingError(f"Failed to read image file: {exc}")

        try:
            user_instruction = (
                "You are given a viewport screenshot of a single Web UI state. "
                "Using the system instructions above, extract all user behavior-level test "
                "scenario specifications that are visually supported by this UI state. "
                "Return ONLY one valid JSON object that strictly follows the required "
                "output schema defined in the system instructions. Do not include any "
                "markdown, comments, or free-form explanation. The JSON must be "
                "syntactically valid and ready for machine parsing."
            )

            response = self._client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_text(text=user_instruction),
                    pil_image_to_part(img),
                ],
                config=default_generate_config(system_instruction=self.system_prompt),
            )
            content = response.text

            logger.debug("--- RAW LLM OUTPUT START (%s) ---", self.model_name)
            logger.debug(content)
            logger.debug("--- RAW LLM OUTPUT END (%s) ---", self.model_name)

            if not content:
                raise AIProcessingError("Received empty response from Gemini")

            return content
        except Exception as exc:
            logger.error("Gemini processing error: %s", exc)
            raise AIProcessingError(f"AI Processing failed: {exc}")
