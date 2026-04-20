import base64
import logging
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.services.llm_provider import LLMProvider

# Configure logging
logger = logging.getLogger(__name__)

class OpenAIService(LLMProvider):
    provider_name = "openai"

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model_name = model_name

    def _encode_image(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            raise AIProcessingError(f"Failed to read image file: {str(e)}")

    def generate(
        self,
        image_path: str,
        *,
        prompt_text: str,
        temperature: float,
        context_text: str | None = None,
        user_instruction: str | None = None,
    ) -> str:
        base64_image = self._encode_image(image_path)
        ext = image_path.lower().split(".")[-1]
        mime_type = "image/png" if ext == "png" else "image/jpeg"

        user_text = ""
        if context_text:
            user_text += f"{context_text}\n\n"
        if user_instruction:
            user_text += f"{user_instruction}"
            
        if not user_text.strip():
            user_text = "Analyze this image according to the system instructions."

        try:
            logger.info(f"Sending request to OpenAI for image: {image_path}")
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": prompt_text
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_text
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                temperature=1
            )
            
            content = response.choices[0].message.content
            
            # Log raw output
            logger.info("--- RAW LLM OUTPUT START ---")
            logger.info(content)
            logger.info("--- RAW LLM OUTPUT END ---")

            if not content:
                raise AIProcessingError("Received empty response from OpenAI")
            
            return content

        except Exception as e:
            logger.error(f"OpenAI API connection failed or processing error: {e}")
            raise AIProcessingError(f"AI Processing failed: {str(e)}")
