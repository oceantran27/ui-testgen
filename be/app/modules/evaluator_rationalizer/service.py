import json
import logging
import re
from typing import TYPE_CHECKING

import google.generativeai as genai
from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.modules.evaluator_rationalizer.models import (
    EvaluationMetadata,
    EvaluationResult,
    EvaluatorPatchedPayload,
    ScenarioEvaluationPatch,
)
from app.modules.evaluator_rationalizer.prompt_loader import load_evaluator_rationalizer_prompt
from app.modules.vision_extractor.json_processor import extract_and_minify_json

if TYPE_CHECKING:
    from app.modules.vision_extractor.models import PageOverview, VisionExtractionPayload

logger = logging.getLogger(__name__)


class EvaluatorRationalizerService:
    def evaluate(
        self,
        extraction_payload: "VisionExtractionPayload",
        model_name: str | None = None,
    ) -> EvaluationResult:
        selected_model = self._normalize_model_name(model_name)
        system_prompt = load_evaluator_rationalizer_prompt()
        expected_scenarios = extraction_payload.scenarios
        expected_scenario_ids = [scenario.id for scenario in expected_scenarios]

        input_payload_json = json.dumps(
            extraction_payload.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )

        raw_output = self._invoke_llm(
            model_name=selected_model,
            system_prompt=system_prompt,
            input_payload_json=input_payload_json,
            expected_scenario_ids=expected_scenario_ids,
        )
        logger.info("--- RAW EVALUATOR OUTPUT START ---")
        logger.info(raw_output)
        logger.info("--- RAW EVALUATOR OUTPUT END ---")

        normalized_output = extract_and_minify_json(raw_output)
        if not normalized_output:
            raise AIProcessingError("Evaluator returned invalid JSON output")

        try:
            patched_payload = EvaluatorPatchedPayload.model_validate(
                json.loads(normalized_output)
            )
        except Exception as exc:
            logger.error("Evaluator output schema mismatch: %s", exc)
            raise AIProcessingError(f"Evaluator output schema mismatch: {exc}")

        actual_by_key: dict[str, ScenarioEvaluationPatch] = {}
        for item in patched_payload.scenarios:
            canonical = self._canonical_id(item.id)
            if canonical not in actual_by_key:
                actual_by_key[canonical] = item

        expected_by_key = {
            self._canonical_id(scenario.id): scenario
            for scenario in expected_scenarios
        }
        missing_keys = [
            key for key in expected_by_key
            if key not in actual_by_key
        ]

        if missing_keys:
            logger.warning(
                "Evaluator output is missing %s scenario(s): %s. Running per-scenario fallback.",
                len(missing_keys),
                ", ".join(expected_by_key[key].id for key in missing_keys),
            )
            for key in missing_keys:
                scenario = expected_by_key[key]
                recovered = self._evaluate_single_scenario_fallback(
                    page_overview=extraction_payload.page_overview,
                    scenario=scenario,
                    model_name=selected_model,
                    system_prompt=system_prompt,
                )
                actual_by_key[key] = recovered

        unresolved_keys = [
            key for key in expected_by_key
            if key not in actual_by_key
        ]
        if unresolved_keys:
            unresolved_ids = [expected_by_key[key].id for key in unresolved_keys]
            raise AIProcessingError(
                f"Evaluator output missing scenarios: {', '.join(unresolved_ids)}"
            )

        scenario_evaluations: list[ScenarioEvaluationPatch] = []
        for scenario in expected_scenarios:
            evaluated = actual_by_key.get(self._canonical_id(scenario.id))
            if not evaluated:
                raise AIProcessingError(
                    f"Evaluator output missing scenario id '{scenario.id}'"
                )

            self._validate_rationale_grounding(
                rationale=evaluated.evaluation.rationale,
                actor=scenario.actor,
                page_overview=extraction_payload.page_overview,
                scenario_id=scenario.id,
            )
            scenario_evaluations.append(evaluated)

        metadata = EvaluationMetadata(
            evaluator_model=selected_model,
            prompt_version=settings.EVALUATOR_RATIONALIZER_PROMPT_VERSION,
            scenario_count=len(scenario_evaluations),
        )

        return EvaluationResult(
            metadata=metadata,
            scenario_evaluations=scenario_evaluations,
        )

    def _invoke_llm(
        self,
        model_name: str,
        system_prompt: str,
        input_payload_json: str,
        expected_scenario_ids: list[str],
    ) -> str:
        if model_name == "openai":
            return self._invoke_openai(system_prompt, input_payload_json, expected_scenario_ids)
        return self._invoke_gemini(model_name, system_prompt, input_payload_json, expected_scenario_ids)

    def _invoke_openai(
        self,
        system_prompt: str,
        input_payload_json: str,
        expected_scenario_ids: list[str],
    ) -> str:
        if not settings.OPENAI_API_KEY:
            raise AIProcessingError("OPENAI_API_KEY is not configured in settings")

        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": self._build_user_instruction(
                            input_payload_json,
                            expected_scenario_ids,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=4000,
                temperature=0,
            )
            content = response.choices[0].message.content
            if not content:
                raise AIProcessingError("Received empty response from OpenAI")
            return content
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("OpenAI evaluator processing error: %s", exc)
            raise AIProcessingError(f"AI evaluator processing failed: {exc}")

    def _invoke_gemini(
        self,
        model_name: str,
        system_prompt: str,
        input_payload_json: str,
        expected_scenario_ids: list[str],
    ) -> str:
        if not settings.GEMINI_API_KEY:
            raise AIProcessingError("GEMINI_API_KEY is not configured in settings")

        actual_model = "gemini-2.5-flash" if model_name == "gemini" else model_name

        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model = genai.GenerativeModel(
                actual_model,
                generation_config={
                    "temperature": 0.0,
                },
            )
            response = model.generate_content(
                [
                    system_prompt,
                    self._build_user_instruction(
                        input_payload_json,
                        expected_scenario_ids,
                    ),
                ]
            )
            content = response.text
            if not content:
                raise AIProcessingError("Received empty response from Gemini")
            return content
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("Gemini evaluator processing error: %s", exc)
            raise AIProcessingError(f"AI evaluator processing failed: {exc}")

    @staticmethod
    def _build_user_instruction(
        input_payload_json: str,
        expected_scenario_ids: list[str],
    ) -> str:
        ids_text = ", ".join(expected_scenario_ids)
        scenario_count = len(expected_scenario_ids)
        return (
            "Evaluate every scenario independently using the system rules and return only one valid JSON object. "
            f"You MUST return exactly {scenario_count} scenarios with these exact ids (no rename): [{ids_text}]. "
            "Input JSON from Module 1 is below:\n"
            f"{input_payload_json}"
        )

    def _evaluate_single_scenario_fallback(
        self,
        page_overview: "PageOverview",
        scenario,
        model_name: str,
        system_prompt: str,
    ) -> ScenarioEvaluationPatch:
        single_payload_json = json.dumps(
            {
                "page_overview": page_overview.model_dump(mode="json"),
                "scenarios": [
                    scenario.model_dump(mode="json", exclude={"evaluation"}),
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

        raw_output = self._invoke_llm(
            model_name=model_name,
            system_prompt=system_prompt,
            input_payload_json=single_payload_json,
            expected_scenario_ids=[scenario.id],
        )
        normalized_output = extract_and_minify_json(raw_output)
        if not normalized_output:
            raise AIProcessingError(
                f"Fallback evaluator returned invalid JSON for scenario '{scenario.id}'"
            )

        try:
            patched_payload = EvaluatorPatchedPayload.model_validate(
                json.loads(normalized_output)
            )
        except Exception as exc:
            raise AIProcessingError(
                f"Fallback evaluator output schema mismatch for scenario '{scenario.id}': {exc}"
            )

        if not patched_payload.scenarios:
            raise AIProcessingError(
                f"Fallback evaluator returned no scenarios for '{scenario.id}'"
            )

        candidate = patched_payload.scenarios[0]
        return ScenarioEvaluationPatch(
            id=scenario.id,
            evaluation=candidate.evaluation,
        )

    @staticmethod
    def _normalize_model_name(model_name: str | None) -> str:
        selected_model = (model_name or "gemini-2.5-flash").strip().lower()
        if selected_model == "openai":
            return "openai"
        if selected_model in {"gemini", "gemini-2.5-flash", "gemini-1.5-flash"}:
            return selected_model
        return "gemini-2.5-flash"

    def _validate_rationale_grounding(
        self,
        rationale: str,
        actor: str,
        page_overview: "PageOverview",
        scenario_id: str,
    ) -> None:
        rationale_lower = rationale.strip().lower()
        if not rationale_lower:
            raise AIProcessingError(
                f"Scenario '{scenario_id}' has empty rationale"
            )

        context_tokens = set()
        context_tokens.update(self._tokenize(actor))
        context_tokens.update(self._tokenize(page_overview.target_users))
        context_tokens.update(self._tokenize(page_overview.functionality))
        for rule in page_overview.business_rules:
            context_tokens.update(self._tokenize(rule))

        if not context_tokens:
            return

        if not any(token in rationale_lower for token in context_tokens):
            raise AIProcessingError(
                f"Scenario '{scenario_id}' rationale must reference page_overview or actor context"
            )

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {
            token
            for token in re.split(r"[^a-z0-9]+", text.lower())
            if token and len(token) >= 3
        }

    @staticmethod
    def _canonical_id(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]", "", value.lower())
        return normalized or value.lower()
