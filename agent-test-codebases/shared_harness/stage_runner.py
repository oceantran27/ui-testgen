from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.api.v1.endpoints.json_utils import extract_and_minify_json
from app.core.exceptions import AIProcessingError
from app.services.llm_provider import LLMProviderFactory

from .kpi import estimate_cost_usd, estimate_tokens
from .models import StageRunMetrics, StageRunResult


def _format_validation_errors(exc: ValidationError, max_items: int = 3) -> str:
    messages: list[str] = []
    for error in exc.errors()[:max_items]:
        location = ".".join(str(item) for item in error.get("loc", [])) or "root"
        message = str(error.get("msg", "validation error"))
        messages.append(f"{location}: {message}")
    return "; ".join(messages) if messages else str(exc)


class StageRunner:
    def __init__(self, *, provider_name: str, model_name: str):
        self.provider = LLMProviderFactory.create(provider_name=provider_name, model_name=model_name)

    def run_stage(
        self,
        *,
        stage_name: str,
        prompt_text: str,
        temperature: float,
        image_path: str,
        context_text: str | None,
        user_instruction: str,
        schema_model: type[BaseModel],
        max_retries: int = 1,
    ) -> StageRunResult:
        first_error: Exception | None = None

        for attempt in range(max_retries + 1):
            used_temperature = temperature if attempt == 0 else 0.0
            strict_suffix = (
                "\n\nSTRICT OUTPUT REQUIREMENT: Output ONLY one valid JSON object. "
                "No markdown. No comments. No extra text."
                if attempt > 0
                else ""
            )

            t0 = time.time()
            try:
                raw_text = self.provider.generate(
                    image_path,
                    prompt_text=prompt_text,
                    temperature=used_temperature,
                    context_text=context_text,
                    user_instruction=user_instruction + strict_suffix,
                )

                minified = extract_and_minify_json(raw_text)
                if not minified:
                    raise AIProcessingError(f"Stage {stage_name} output did not contain valid JSON")

                try:
                    parsed: dict[str, Any] = json.loads(minified)
                except Exception as exc:
                    raise AIProcessingError(f"Stage {stage_name} output contained malformed JSON") from exc

                try:
                    validated = schema_model.model_validate(parsed)
                except ValidationError as exc:
                    details = _format_validation_errors(exc)
                    raise AIProcessingError(f"Stage {stage_name} schema validation failed: {details}") from exc

                elapsed_ms = int((time.time() - t0) * 1000)
                prompt_payload = prompt_text + (context_text or "") + user_instruction
                prompt_tokens = estimate_tokens(prompt_payload)
                output_tokens = estimate_tokens(raw_text)
                total_tokens = prompt_tokens + output_tokens

                metrics = StageRunMetrics(
                    stage_name=stage_name,
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    temperature=used_temperature,
                    requested_temperature=temperature,
                    attempts=attempt + 1,
                    elapsed_ms=elapsed_ms,
                    prompt_token_estimate=prompt_tokens,
                    output_token_estimate=output_tokens,
                    total_token_estimate=total_tokens,
                    cost_usd_estimate=estimate_cost_usd(self.provider.model_name, prompt_tokens, output_tokens),
                )
                return StageRunResult(
                    raw_text=raw_text,
                    parsed_json=parsed,
                    validated_json=validated.model_dump(mode="json"),
                    metrics=metrics,
                )
            except Exception as exc:  # pragma: no cover - retry path behavior
                if first_error is None:
                    first_error = exc
                if attempt >= max_retries:
                    raise AIProcessingError(
                        f"Stage {stage_name} failed after retry. First error: {first_error}. Retry error: {exc}"
                    ) from exc

        raise AIProcessingError(f"Stage {stage_name} failed unexpectedly")
