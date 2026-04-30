import logging

from app.core.config import settings
from app.modules.vision_extractor.providers.gemini_provider import GeminiVisionProvider
from app.services.prompt_service import load_system_prompt

logger = logging.getLogger(__name__)


class GeminiService:
    """Delegates to GeminiVisionProvider — same Gemini path as the vision extractor factory."""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured in settings")
        self._provider = GeminiVisionProvider(
            system_prompt=load_system_prompt(),
            model_name=model_name,
        )

    def analyze_image(self, image_path: str) -> str:
        logger.info("Sending request to Gemini for image: %s", image_path)
        return self._provider.analyze_image(image_path)
