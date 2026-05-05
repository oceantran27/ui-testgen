import base64

import logging

from pathlib import Path



from openai import OpenAI



from app.core.config import settings

from app.core.exceptions import AIProcessingError

from app.schemas.test_scenario_generation import TestScenarioSuite

from app.services.prompt_service import (
    load_single_stage_test_scenario_prompt,
    load_two_stage_test_scenario_prompt,
    load_ui_extraction_prompt,
)

from app.services.test_scenario_payload import parse_test_scenario_suite_payload



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

    """OpenAI client for single-stage test scenarios and two-stage UI extraction → scenarios."""



    def __init__(self, model_name: str = "gpt-4.1"):

        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

        self.model = model_name



    def _encode_image(self, image_path: str) -> str:

        try:

            with open(image_path, "rb") as image_file:

                return base64.b64encode(image_file.read()).decode("utf-8")

        except Exception as e:

            logger.error("Failed to encode image: %s", e)

            raise AIProcessingError(f"Failed to read image file: {str(e)}") from e



    def generate_test_scenarios_from_image(self, image_path: str) -> TestScenarioSuite:

        if not settings.OPENAI_API_KEY:

            raise AIProcessingError("OPENAI_API_KEY is not configured")

        system_prompt = load_single_stage_test_scenario_prompt()

        base64_image = self._encode_image(image_path)

        mime_type = _mime_type_for_path(image_path)

        user_text = (

            "Analyze this UI screenshot and output the test scenario JSON exactly as specified in the system instructions. "

            "Return exactly one JSON object with the required shape (feature and scenarios). "

            "Do not include markdown, code fences, or extra text."

        )

        try:

            logger.info(

                "Sending OpenAI single-stage test scenario request for image: %s model=%s",

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

            logger.error("OpenAI single-stage test scenario generation failed: %s", exc)

            raise AIProcessingError(f"Test scenario generation failed: {exc}") from exc

        content = response.choices[0].message.content

        if not content:

            raise AIProcessingError("Received empty response from OpenAI")

        logger.debug("Single-stage raw output length (OpenAI): %s", len(content))

        return parse_test_scenario_suite_payload(content, result_model=self.model)



    def generate_ui_extraction_raw(self, image_path: str) -> str:

        if not settings.OPENAI_API_KEY:

            raise AIProcessingError("OPENAI_API_KEY is not configured")

        system_prompt = load_ui_extraction_prompt()

        base64_image = self._encode_image(image_path)

        mime_type = _mime_type_for_path(image_path)

        user_text = (

            "Analyze this UI screenshot and output the UI extraction JSON (stage 1) exactly as specified. "

            "Return exactly one JSON object. Do not include markdown, code fences, or extra text."

        )

        try:

            logger.info(

                "Sending OpenAI UI extraction request for image: %s model=%s",

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

            logger.error("OpenAI UI extraction failed: %s", exc)

            raise AIProcessingError(f"UI extraction failed: {exc}") from exc

        content = response.choices[0].message.content

        if not content:

            raise AIProcessingError("Received empty response from OpenAI (UI extraction)")

        logger.debug("UI extraction raw output length (OpenAI): %s", len(content))

        return content



    def generate_two_stage_test_scenarios_from_hierarchy(

        self, extraction_json: str, *, result_model: str

    ) -> TestScenarioSuite:

        if not settings.OPENAI_API_KEY:

            raise AIProcessingError("OPENAI_API_KEY is not configured")

        system_prompt = load_two_stage_test_scenario_prompt()

        user_text = (

            "UI extraction JSON from stage 1 (sole source of truth for visible UI wording):\n"

            f"{extraction_json}\n\n"

            "Produce the test scenario suite JSON per the system instructions. Return exactly one JSON object. "

            "Do not include markdown, code fences, or extra text."

        )

        try:

            logger.info("Sending OpenAI two-stage test scenario request model=%s", self.model)

            response = self.client.chat.completions.create(

                model=self.model,

                messages=[

                    {"role": "system", "content": system_prompt},

                    {"role": "user", "content": user_text},

                ],

                response_format={"type": "json_object"},

            )

        except Exception as exc:

            logger.error("OpenAI two-stage test scenario generation failed: %s", exc)

            raise AIProcessingError(f"Test scenario generation failed: {exc}") from exc

        content = response.choices[0].message.content

        if not content:

            raise AIProcessingError("Received empty response from OpenAI (two-stage scenarios)")

        logger.debug("Two-stage scenario raw output length (OpenAI): %s", len(content))

        return parse_test_scenario_suite_payload(content, result_model=result_model)

