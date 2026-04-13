import asyncio
import json
import logging
import threading
from typing import Any

import google.generativeai as genai
from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.core.model_selection import normalize_analysis_model_name, resolve_gemini_model_name
from app.modules.vision_extractor.json_processor import extract_and_minify_json

try:
    from openai import RateLimitError as OpenAIRateLimitError
except Exception:  # pragma: no cover - defensive import fallback
    OpenAIRateLimitError = None

logger = logging.getLogger(__name__)


class CommitteeTimeoutError(Exception):
    pass


class CommitteeRateLimitError(Exception):
    pass


class CommitteeLLMClient:
    def __init__(self):
        self._openai_client: OpenAI | None = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self._openai_lock = threading.Lock()
        self._gemini_models: dict[str, genai.GenerativeModel] = {}
        self._gemini_lock = threading.Lock()
        self._gemini_configured = False

    async def invoke_json(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        timeout_seconds = settings.COMMITTEE_LLM_TIMEOUT_SECONDS

        try:
            raw_output = await asyncio.wait_for(
                asyncio.to_thread(
                    self._invoke_sync,
                    model_name,
                    system_prompt,
                    user_payload,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise CommitteeTimeoutError(
                f"Committee LLM call timed out after {timeout_seconds} seconds"
            ) from exc
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                raise CommitteeRateLimitError(f"Committee LLM rate limit: {exc}") from exc
            if self._is_timeout_error(exc):
                raise CommitteeTimeoutError(f"Committee LLM timeout: {exc}") from exc
            raise AIProcessingError(f"Committee LLM call failed: {exc}") from exc

        normalized_output = extract_and_minify_json(raw_output)
        if not normalized_output:
            raise AIProcessingError("Committee LLM returned invalid JSON output")

        try:
            return json.loads(normalized_output)
        except Exception as exc:
            raise AIProcessingError(f"Committee LLM JSON parse failed: {exc}") from exc

    def _invoke_sync(
        self,
        model_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        normalized_model = self._normalize_model_name(model_name)
        payload_json = json.dumps(
            user_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        if normalized_model == "openai":
            return self._invoke_openai(system_prompt=system_prompt, payload_json=payload_json)
        return self._invoke_gemini(
            model_name=normalized_model,
            system_prompt=system_prompt,
            payload_json=payload_json,
        )

    @staticmethod
    def _normalize_model_name(model_name: str | None) -> str:
        return normalize_analysis_model_name(model_name)

    @staticmethod
    def _build_user_instruction(payload_json: str) -> str:
        return (
            "Use the system instructions and return exactly one valid JSON object. "
            "Do not return markdown, code fences, or explanatory text. "
            "Input payload JSON is below:\n"
            f"{payload_json}"
        )

    def _invoke_openai(self, *, system_prompt: str, payload_json: str) -> str:
        try:
            client = self._get_openai_client()
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": self._build_user_instruction(payload_json),
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
        except Exception as exc:
            logger.error("Committee OpenAI processing error: %s", exc)
            raise

    def _invoke_gemini(self, *, model_name: str, system_prompt: str, payload_json: str) -> str:
        try:
            model = self._get_gemini_model(model_name)
            response = model.generate_content(
                [
                    system_prompt,
                    self._build_user_instruction(payload_json),
                ]
            )
            content = response.text
            if not content:
                raise AIProcessingError("Received empty response from Gemini")
            return content
        except Exception as exc:
            logger.error("Committee Gemini processing error: %s", exc)
            raise

    def _get_openai_client(self) -> OpenAI:
        if not settings.OPENAI_API_KEY:
            raise AIProcessingError("OPENAI_API_KEY is not configured in settings")

        if self._openai_client is not None:
            return self._openai_client

        with self._openai_lock:
            if self._openai_client is None:
                self._openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            return self._openai_client

    def _get_gemini_model(self, model_name: str) -> genai.GenerativeModel:
        if not settings.GEMINI_API_KEY:
            raise AIProcessingError("GEMINI_API_KEY is not configured in settings")

        actual_model = resolve_gemini_model_name(model_name)
        with self._gemini_lock:
            if not self._gemini_configured:
                genai.configure(api_key=settings.GEMINI_API_KEY)
                self._gemini_configured = True

            model = self._gemini_models.get(actual_model)
            if model is None:
                model = genai.GenerativeModel(
                    actual_model,
                    generation_config={
                        "temperature": 0.0,
                    },
                )
                self._gemini_models[actual_model] = model

        return model

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        if OpenAIRateLimitError and isinstance(exc, OpenAIRateLimitError):
            return True

        exc_name = exc.__class__.__name__.lower()
        message = str(exc).lower()

        return (
            "ratelimit" in exc_name
            or "toomanyrequests" in exc_name
            or "resourceexhausted" in exc_name
            or "429" in message
            or "rate limit" in message
            or "too many requests" in message
            or "resource exhausted" in message
        )

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        exc_name = exc.__class__.__name__.lower()
        message = str(exc).lower()
        return "timeout" in exc_name or "timed out" in message or "deadline" in message
