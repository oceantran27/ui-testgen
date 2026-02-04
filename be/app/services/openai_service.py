import base64
import json
import logging
from openai import OpenAI
from app.core.config import settings
from app.core.exceptions import AIProcessingError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = "gpt-4o"
        self.system_prompt = self._load_system_prompt()

    def _encode_image(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            raise AIProcessingError(f"Failed to read image file: {str(e)}")

    def _load_system_prompt(self) -> str:
        try:
            prompt_path = "app/prompts/system_prompt.txt"
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            raise AIProcessingError(f"Failed to load system prompt: {str(e)}")

    def analyze_image(self, image_path: str) -> dict:
        base64_image = self._encode_image(image_path)

        try:
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
                            {"type": "text", "text": "Analyze this web interface image and list the functions that have been set up according to the requirements."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
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
            if not content:
                raise AIProcessingError("Received empty response from OpenAI")
            
            # The API is now expected to return a JSON string.
            return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from OpenAI: {e}")
            raise AIProcessingError(f"Failed to parse JSON response: {str(e)}")
        except Exception as e:
            logger.error(f"GPT-4o API connection failed or processing error: {e}")
            raise AIProcessingError(f"AI Processing failed: {str(e)}")
