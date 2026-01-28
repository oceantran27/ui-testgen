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

    def _encode_image(self, image_path: str) -> str:
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            raise AIProcessingError(f"Failed to read image file: {str(e)}")

    def analyze_image(self, image_path: str) -> dict:
        base64_image = self._encode_image(image_path)

        system_prompt = (
            "### ROLE\n"
            "You are an expert QA Automation Architect specializing in Semantic UI Analysis and Test Generation. "
            "You possess deep knowledge of User Experience (UX) patterns and Business Process Modeling.\n\n"

            "### CONTEXT\n"
            "You are provided with a screenshot of a software application's user interface. "
            "The goal is to generate high-level test scenarios that describe *user intentions* rather than mechanical interactions. "
            "These scenarios will be used to create semantic automated tests.\n\n"

            "### TASK\n"
            "Analyze the visual elements in the screenshot and extract a list of abstract, high-level user intentions in Vietnamese.\n\n"

            "### REASONING STRATEGY (CHAIN OF THOUGHT)\n"
            "1. **Identify Components**: Scan the image to locate functional groups (e.g., Navigation Bar, Login Form, Search Bar, Data Grid, Action Buttons).\n"
            "2. **Infer Purpose**: For each group, determine the business goal. Ask: 'What is the user trying to achieve here?'\n"
            "3. **Abstract Mechanics**: Ignore specific UI widgets (textboxes, dropdowns). Merge sequences of steps (e.g., fill form + submit) into a single intent.\n"
            "4. **Translate**: Convert the intent into natural, professional Vietnamese.\n\n"

            "### CONSTRAINTS & STOP CONDITIONS\n"
            "- **STRICTLY FORBIDDEN**: Do NOT use low-level interaction verbs like 'Click', 'Type', 'Select', 'Tap', 'Press', 'Hover'.\n"
            "- **Language**: Output must be in **Vietnamese**.\n"
            "- **Granularity**: Focus on the 'What' (Business Goal), not the 'How' (UI Mechanics).\n"
            "- **Completeness**: Cover all primary actions visible in the screenshot.\n\n"

            "### EXAMPLES\n"
            "- *Input*: Login screen with username, password, and login button.\n"
            "  - *Negative*: 'Click vào ô username, gõ admin, click ô password, gõ 123, click nút Login.'\n"
            "  - *Positive*: 'Đăng nhập vào hệ thống với tài khoản hợp lệ.'\n"
            "- *Input*: E-commerce product page with size/color selection and 'Add to Cart'.\n"
            "  - *Negative*: 'Chọn size L, chọn màu Xanh, click nút Thêm vào giỏ.'\n"
            "  - *Positive*: 'Thêm sản phẩm vào giỏ hàng với tùy chọn Size L và Màu Xanh.'\n\n"

            "### OUTPUT FORMAT\n"
            "Return a valid JSON object with the following structure:\n"
            "{\n"
            "  \"scenarios\": [\n"
            "    {\n"
            "      \"category\": \"<Functional Area, e.g., Authentication, Search>\",\n"
            "      \"intention\": \"<The high-level user intention in Vietnamese>\"\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Analyze this UI and extract high-level user intentions based on the defined strategy."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            
            content = response.choices[0].message.content
            if not content:
                raise AIProcessingError("Received empty response from OpenAI")
                
            return json.loads(content)

        except Exception as e:
            logger.error(f"GPT-4o API connection failed or processing error: {e}")
            raise AIProcessingError(f"AI Processing failed: {str(e)}")
