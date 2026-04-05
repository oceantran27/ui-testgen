import base64
import logging

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.services.prompt_service import load_system_prompt

# Configure logging
logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self, model_name: str = "gpt-4.1"):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model_name
        self.system_prompt = load_system_prompt()

    def _encode_image(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            raise AIProcessingError(f"Failed to read image file: {str(e)}")

    def analyze_image(self, image_path: str) -> str:
        base64_image = self._encode_image(image_path)
        ext = image_path.lower().split(".")[-1]
        mime_type = "image/png" if ext == "png" else "image/jpeg"

        try:
            logger.info(f"Sending request to OpenAI for image: {image_path}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self.system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Analyze this web UI screenshot using the system instructions and return exactly one valid JSON object "
                                    "that follows the required schema with page_overview, scenarios, and business_rules_and_constraints. "
                                    "Do not return markdown, code fences, or extra text."
                                )
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
                response_format={"type": "json_object"},
                max_tokens=4000,
                temperature=0
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
