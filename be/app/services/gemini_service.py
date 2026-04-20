import logging

from google import genai
from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class GeminiService(LLMProvider):
    provider_name = "gemini"

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured in settings")

        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = model_name

    def generate(
        self,
        image_path: str,
        *,
        prompt_text: str,
        temperature: float,
        context_text: str | None = None,
        user_instruction: str | None = None,
    ) -> str:
        try:
            img = Image.open(image_path)
        except Exception as exc:
            logger.error("Failed to open image: %s", exc)
            raise AIProcessingError(f"Failed to read image file: {str(exc)}") from exc

        try:
            logger.info("Sending request to Gemini for image: %s", image_path)

            # Parts ordering matters: prompt (role), then structured context, then user instruction, then image.
            parts: list[object] = [prompt_text]
            if context_text:
                parts.append(context_text)
            if user_instruction:
                parts.append(user_instruction)
            parts.append(img)

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=parts,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                )
            )
            content = getattr(response, "text", None)

            logger.info("--- RAW LLM OUTPUT START ---")
            logger.info(content)
            logger.info("--- RAW LLM OUTPUT END ---")

            if not content:
                raise AIProcessingError("Received empty response from Gemini")

            return str(content)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("Gemini API connection failed or processing error: %s", exc)
            raise AIProcessingError(f"AI Processing failed: {str(exc)}") from exc
