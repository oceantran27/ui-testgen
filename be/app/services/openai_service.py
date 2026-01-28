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
            "You are an Expert AI Test Automation Architect specializing in Declarative Testing, Business-Driven Development (BDD), and Semantic UI Analysis.\n\n"
            
            "### CONTEXT\n"
            "You are provided with a screenshot of a software application's user interface. "
            "Your goal is to identify potential user interactions and translate them into **High-Level Abstract Actions** (also known as Business Intents or Semantic Actions) that will be used to create automated tests.\n\n"

            "### TASK\n"
            "Analyze the visual elements in the screenshot and extract a list of abstract, high-level user intentions. "
            "The final output must be in **English**.\n\n"
            
            "### CRITICAL INSTRUCTIONS (The Golden Rule)\n"
            "You must strictly adhere to the declarative style.\n"
            "* **DO NOT** describe low-level imperative UI interactions. Avoid phrases like 'click the button', 'type in the text box', 'select from dropdown', 'hover over element'.\n"
            "* **DO** describe the **business goal** or the **outcome** of the interaction sequence.\n"
            "* If an action involves selecting multiple options (e.g., a product card with color, size, quantity), encapsulate all those selections into a single, parameterized high-level action statement.\n"
            "* **CONTEXTUAL INFERENCE:** You must carefully read and analyze all visible text, labels, headers, and active tab names to infer the user's true intent. The label of a container (e.g., a Tab or Header) often defines the goal of the input fields inside it.\n"
            "    * *Rule:* If an action looks like a 'Search' but is located inside a 'Buy/Booking' tab, the intent is 'Buy/Book', not 'Search'.\n\n"

            "### REASONING STRATEGY (How to think)\n"
            "Before generating the output, apply the following reasoning steps for each potential action:\n"
            "1.  **Observe Context:** Look at the parent container of the elements. Is there a Tab name? A Section Header? (e.g., 'Buy Tickets', 'Registration', 'Settings').\n"
            "2.  **Read Elements:** Read the input labels (e.g., 'From', 'To', 'Date').\n"
            "3.  **Synthesize Intent:** Combine the Context + Elements.\n"
            "    * *Logic:* [Context: 'Buy Ticket'] + [Inputs: 'Hanoi', 'Da Nang'] = Intent: 'Buy ticket from Hanoi to Da Nang'.\n"
            "    * *Logic:* [Context: 'Check Status'] + [Input: 'Order ID'] = Intent: 'Track Order Status'.\n"
            "4.  **Format**: Convert the final synthesized intent into natural, professional English.\n\n"

            "### EXAMPLES\n"
            "* **Scenario 1: Login Form**\n"
            "    * *What you see (Visual):* Input field for username, input field for password, a button labeled 'Login'.\n"
            "    * *WRONG Output (Imperative):* 'Type username, type password, click Login button.'\n"
            "    * *CORRECT Output (Declarative Abstract Action):* 'Perform Login' (or 'Login with credentials').\n"
            "\n"
            "* **Scenario 2: E-commerce Product Card**\n"
            "    * *What you see (Visual):* A card for 'Jean Pants X', a dropdown for size (e.g., XXL selected), a color swatch (e.g., Blue selected), a quantity input (e.g., 2), and an 'Add to Cart' icon/button.\n"
            "    * *WRONG Output (Imperative):* 'Select size XXL, select Blue color, type quantity 2, click Add to Cart icon.'\n"
            "    * *CORRECT Output (Declarative Abstract Action):* 'Add 'Jean Pants X' to cart with parameters: Size XXL, Color Blue, Quantity 2.'\n"
            "\n"
            "* **Scenario 3: Flight Booking Tab (Contextual Reasoning Example)**\n"
            "    * *What you see (Visual):* A search bar with inputs 'From: Hanoi', 'To: Da Nang', 'Date: 20/10/2024'. Critically, these inputs are located inside an active Tab labeled **'Mua vé' (Buy Ticket)**.\n"
            "    * *WRONG Output (Literal/Low-level):* 'Search flights from Hanoi to Da Nang.' (This ignores the 'Buy' context).\n"
            "    * *CORRECT Output (Intent-Driven):* 'Buy flight ticket from Hanoi to Da Nang departing on 20/10/2024.'\n\n"

            "### OUTPUT FORMAT\n"
            "Return a valid JSON object with the following structure. The 'intention' must be in **English**.\n"
            "{\n"
            "  \"scenarios\": [\n"
            "    {\n"
            "      \"category\": \"<Functional Area, e.g., Authentication, Search>\",\n"
            "      \"intention\": \"<The high-level user intention in English>\"\n"
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
