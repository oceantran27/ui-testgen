import base64
import json
import logging
from functools import lru_cache
import google.generativeai as genai
from PIL import Image
from app.core.config import settings
from app.core.exceptions import AIProcessingError

# Configure logging
logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not configured in settings")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name,
            generation_config={
                "temperature": 0.0,
            },
        )
        self.system_prompt = self.get_system_prompt()

    @staticmethod
    @lru_cache(maxsize=1)
    def get_system_prompt() -> str:
        try:
            prompt_path = "app/prompts/system_prompt.txt"
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            raise AIProcessingError(f"Failed to load system prompt: {str(e)}")

    def analyze_image(self, image_path: str) -> str:
        try:
            img = Image.open(image_path)
        except Exception as e:
            logger.error(f"Failed to open image: {e}")
            raise AIProcessingError(f"Failed to read image file: {str(e)}")

        try:
            logger.info(f"Sending request to Gemini for image: {image_path}")

            user_instruction = (
                "You are given a viewport screenshot of a single Web UI state. "
                "Using the system instructions above, extract all user behavior-level test "
                "scenario specifications that are visually supported by this UI state. "
                "Return ONLY one valid JSON object that strictly follows the required "
                "output schema defined in the system instructions. Do not include any "
                "markdown, comments, or free-form explanation. The JSON must be "
                "syntactically valid and ready for machine parsing."
            )

            prompt_parts = [
                self.system_prompt,
                user_instruction,
                img,
            ]

            response = self.model.generate_content(prompt_parts)
            
            content = response.text
            
            # Log raw output
            logger.info("--- RAW LLM OUTPUT START ---")
            logger.info(content)
            logger.info("--- RAW LLM OUTPUT END ---")

            if not content:
                raise AIProcessingError("Received empty response from Gemini")
            
            return content

        except Exception as e:
            logger.error(f"Gemini API connection failed or processing error: {e}")
            raise AIProcessingError(f"AI Processing failed: {str(e)}")
