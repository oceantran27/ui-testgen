"""
OpenAI Model Provider — Secondary/fallback provider using openai SDK.

Supports text and vision structured output.
"""
from __future__ import annotations

import copy
import json
import time
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.logging import logger
from app.model_providers.base import (
    BaseModelProvider,
    ImageInput,
    ModelCallStatus,
    ModelCapability,
    ModelErrorCode,
    ModelProviderError,
    ModelRequest,
    ModelResponse,
    NonRetryableModelError,
    RequestType,
    RetryableModelError,
    TokenUsage,
)


def _normalize_json_schema_for_openai_strict(node: Any) -> None:
    """
    OpenAI Chat Completions response_format json_schema with strict=True expects each object to set
    additionalProperties=false and to list every property key under required.
    Pydantic model_json_schema() omits these by default — patch recursively ($defs included).
    """
    if isinstance(node, list):
        for item in node:
            _normalize_json_schema_for_openai_strict(item)
        return
    if not isinstance(node, dict):
        return

    defs = node.get("$defs")
    if isinstance(defs, dict):
        for sub in defs.values():
            _normalize_json_schema_for_openai_strict(sub)

    props = node.get("properties")
    if isinstance(props, dict):
        if node.get("type") is None and "$ref" not in node:
            node["type"] = "object"
        elif isinstance(node.get("type"), list) and "object" not in node["type"]:
            node["type"] = "object"
        node["additionalProperties"] = False
        node["required"] = list(props.keys())
        for child in props.values():
            _normalize_json_schema_for_openai_strict(child)

    items = node.get("items")
    if items is not None:
        _normalize_json_schema_for_openai_strict(items)

    for combo_key in ("anyOf", "oneOf", "allOf"):
        combo = node.get(combo_key)
        if isinstance(combo, list):
            for branch in combo:
                _normalize_json_schema_for_openai_strict(branch)

    prefix_items = node.get("prefixItems")
    if isinstance(prefix_items, list):
        for it in prefix_items:
            _normalize_json_schema_for_openai_strict(it)


class OpenAIModelProvider(BaseModelProvider):

    def __init__(self):
        self._client = None

    @staticmethod
    def _strip_json_code_fence(raw_text: str) -> str:
        """If the model wraps JSON in ```json ... ```, extract the inner payload."""
        s = raw_text.strip()
        if not s.startswith("```"):
            return s
        lines = s.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    @staticmethod
    def _uses_restricted_sampling(model_name: str) -> bool:
        """Models that reject custom temperature / max_tokens (use API defaults)."""
        m = model_name.lower()
        return m.startswith("gpt-5") or m.startswith("o1") or m.startswith("o3")

    @staticmethod
    def _chat_completion_token_kwargs(model_name: str, max_output_tokens: int) -> Dict[str, int]:
        """Some Chat Completions models reject max_tokens and require max_completion_tokens."""
        if OpenAIModelProvider._uses_restricted_sampling(model_name):
            return {"max_completion_tokens": max_output_tokens}
        return {"max_tokens": max_output_tokens}

    @staticmethod
    def _chat_completion_temperature_kwargs(model_name: str, temperature: float) -> Dict[str, float]:
        """Some models only allow the default temperature; omit the parameter."""
        if OpenAIModelProvider._uses_restricted_sampling(model_name):
            return {}
        return {"temperature": temperature}

    @property
    def name(self) -> str:
        return "openai"

    @property
    def capabilities(self) -> set[ModelCapability]:
        return {
            ModelCapability.TEXT,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.MULTI_IMAGE,
            ModelCapability.JSON_SCHEMA,
        }

    def _get_client(self):
        if self._client is None:
            import httpx
            import openai
            api_key = settings.OPENAI_API_KEY
            if not api_key:
                raise NonRetryableModelError(ModelProviderError(
                    error_code=ModelErrorCode.MODEL_AUTH_FAILED,
                    provider=self.name, model_name="", task_name="",
                    retryable=False, message="OPENAI_API_KEY is not set"
                ))
            kw: Dict[str, Any] = {"api_key": api_key}
            if settings.DISABLE_MODEL_HTTP_TIMEOUT:
                kw["timeout"] = httpx.Timeout(None)
            self._client = openai.AsyncOpenAI(**kw)
        return self._client

    async def generate(self, request: ModelRequest) -> ModelResponse:
        start_time = time.time()
        # Resolve model name: request-level → vision/text config based on request type
        if request.model_name:
            model_name = request.model_name
        elif request.image_inputs:
            model_name = settings.OPENAI_VISION_MODEL
        else:
            model_name = settings.OPENAI_TEXT_MODEL

        if not model_name:
            raise NonRetryableModelError(ModelProviderError(
                error_code=ModelErrorCode.MODEL_INVALID_REQUEST,
                provider=self.name, model_name="", task_name=request.task_name,
                retryable=False, message="No OpenAI model name configured. Set OPENAI_TEXT_MODEL or OPENAI_VISION_MODEL."
            ))

        try:
            client = self._get_client()

            messages: List[Dict[str, Any]] = []

            # System message
            if request.system_instruction:
                messages.append({"role": "system", "content": request.system_instruction})

            # Build user message content
            user_content: List[Dict[str, Any]] = []

            # Images
            if request.image_inputs:
                for img_input in request.image_inputs:
                    img_data = self._resolve_image_base64(img_input)
                    if img_data:
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{img_input.mime_type};base64,{img_data}"}
                        })

            # Text
            user_text = request.user_instruction
            if request.context_json:
                user_text += f"\n\nContext:\n```json\n{json.dumps(request.context_json, indent=2)}\n```"

            schema_openai_strict: Optional[Dict[str, Any]] = None
            if request.output_schema:
                schema_openai_strict = copy.deepcopy(request.output_schema.model_json_schema())
                schema_openai_strict.get("properties", {}).pop("schema_name", None)
                schema_openai_strict.get("properties", {}).pop("schema_version", None)
                _normalize_json_schema_for_openai_strict(schema_openai_strict)
                schema_hint = json.dumps(schema_openai_strict, indent=2)
                user_text += (
                    "\n\nRespond ONLY with valid JSON matching this schema:\n```json\n"
                    f"{schema_hint}\n```"
                )

            user_content.append({"type": "text", "text": user_text})
            messages.append({"role": "user", "content": user_content})

            # Build response_format using strict json_schema (openai>=1.40.0)
            response_format: Any = {"type": "json_object"}
            if request.output_schema is not None and schema_openai_strict is not None:
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.output_schema.__name__,
                        "strict": True,
                        "schema": schema_openai_strict,
                    },
                }
            elif not request.image_inputs:
                # Only use json_object for text-only requests without schema
                response_format = {"type": "json_object"}

            token_kw = self._chat_completion_token_kwargs(model_name, request.max_output_tokens)
            temp_kw = self._chat_completion_temperature_kwargs(model_name, request.temperature)
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format=response_format,
                **temp_kw,
                **token_kw,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            choice = response.choices[0]
            raw_text = choice.message.content or ""
            finish_reason = getattr(choice, "finish_reason", None) or ""
            if finish_reason == "length":
                raise RetryableModelError(ModelProviderError(
                    error_code=ModelErrorCode.MODEL_PROVIDER_ERROR,
                    provider=self.name, model_name=model_name, task_name=request.task_name,
                    retryable=True,
                    message=(
                        f"OpenAI response truncated (finish_reason=length, {len(raw_text)} chars). "
                        f"Increase max_output_tokens for task '{request.task_name}'."
                    ),
                    details={"finish_reason": finish_reason},
                ))
            if not raw_text:
                raise RetryableModelError(ModelProviderError(
                    error_code=ModelErrorCode.MODEL_EMPTY_RESPONSE,
                    provider=self.name, model_name=model_name, task_name=request.task_name,
                    retryable=True, message="OpenAI returned empty response"
                ))

            parsed = self._parse_and_validate(raw_text, request)

            usage = None
            if response.usage:
                usage = TokenUsage(
                    input_tokens=response.usage.prompt_tokens or 0,
                    output_tokens=response.usage.completion_tokens or 0,
                    total_tokens=response.usage.total_tokens or 0,
                )

            return ModelResponse(
                request_id=request.request_id,
                run_id=request.run_id,
                node_name=request.node_name,
                task_name=request.task_name,
                provider=self.name,
                model_name=model_name,
                request_type=request.request_type,
                status=ModelCallStatus.SUCCESS,
                parsed_output=parsed,
                raw_text=raw_text,
                usage=usage,
                latency_ms=latency_ms,
                image_count=len(request.image_inputs),
            )

        except (RetryableModelError, NonRetryableModelError):
            raise
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            retryable = True
            error_code = ModelErrorCode.MODEL_PROVIDER_ERROR
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                error_code = ModelErrorCode.MODEL_RATE_LIMITED
            elif "authentication" in error_msg.lower() or "401" in error_msg:
                error_code = ModelErrorCode.MODEL_AUTH_FAILED
                retryable = False
            elif "timeout" in error_msg.lower():
                error_code = ModelErrorCode.MODEL_TIMEOUT

            err = ModelProviderError(
                error_code=error_code,
                provider=self.name, model_name=model_name, task_name=request.task_name,
                retryable=retryable, message=error_msg[:500]
            )
            if retryable:
                raise RetryableModelError(err) from e
            raise NonRetryableModelError(err) from e

    def _resolve_image_base64(self, img: ImageInput) -> Optional[str]:
        """Resolve image to base64 string."""
        import base64
        raw_bytes = None
        if img.image_bytes:
            raw_bytes = img.image_bytes
        elif img.storage_uri:
            from app.services.storage_service import storage_service
            try:
                raw_bytes = storage_service.download_from_uri(img.storage_uri)
            except Exception as e:
                logger.warning(f"Failed to download image {img.storage_uri}: {e}")
                return None
        if raw_bytes:
            return base64.b64encode(raw_bytes).decode("utf-8")
        return None

    def _parse_and_validate(self, raw_text: str, request: ModelRequest) -> Union[BaseModel, Dict[str, Any]]:
        """Parse JSON and validate against Pydantic schema. Returns the model instance when schema is set."""
        payload = self._strip_json_code_fence(raw_text)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as e:
            tail = payload[-400:] if len(payload) > 400 else payload
            raise RetryableModelError(ModelProviderError(
                error_code=ModelErrorCode.MODEL_INVALID_JSON,
                provider=self.name, model_name=request.model_name, task_name=request.task_name,
                retryable=True,
                message=f"Invalid JSON from model: {e}",
                details={
                    "raw_text_len": len(payload),
                    "raw_text_head": payload[:200],
                    "raw_text_tail": tail,
                },
            )) from e

        if request.output_schema:
            try:
                validated = request.output_schema.model_validate(parsed)
                return validated
            except ValidationError as e:
                raise RetryableModelError(ModelProviderError(
                    error_code=ModelErrorCode.MODEL_SCHEMA_MISMATCH,
                    provider=self.name, model_name=request.model_name, task_name=request.task_name,
                    retryable=True, message=f"Schema validation failed: {e}",
                    details={"validation_errors": e.errors()},
                )) from e

        return parsed
