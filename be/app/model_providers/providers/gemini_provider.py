"""
Gemini Model Provider — Primary VLM/LLM provider using google-genai SDK.

Supports text and vision structured output via Gemini's response_schema.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional, Union

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


class GeminiModelProvider(BaseModelProvider):

    def __init__(self):
        self._client = None

    @property
    def name(self) -> str:
        return "gemini"

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
            from google import genai
            api_key = settings.GEMINI_API_KEY
            if not api_key:
                raise NonRetryableModelError(ModelProviderError(
                    error_code=ModelErrorCode.MODEL_AUTH_FAILED,
                    provider=self.name, model_name="", task_name="",
                    retryable=False, message="GEMINI_API_KEY is not set"
                ))
            self._client = genai.Client(api_key=api_key)
        return self._client

    async def generate(self, request: ModelRequest) -> ModelResponse:
        start_time = time.time()
        # Resolve model name: request-level → vision/text config based on request type
        if request.model_name:
            model_name = request.model_name
        elif request.image_inputs:
            model_name = settings.GEMINI_VISION_MODEL
        else:
            model_name = settings.GEMINI_TEXT_MODEL

        if not model_name:
            raise NonRetryableModelError(ModelProviderError(
                error_code=ModelErrorCode.MODEL_INVALID_REQUEST,
                provider=self.name, model_name="", task_name=request.task_name,
                retryable=False, message="No Gemini model name configured. Set GEMINI_TEXT_MODEL or GEMINI_VISION_MODEL."
            ))

        try:
            client = self._get_client()

            # Build contents
            contents = []

            # Add image parts for vision requests
            if request.image_inputs:
                for img_input in request.image_inputs:
                    img_bytes = self._resolve_image(img_input)
                    if img_bytes:
                        from google.genai import types
                        contents.append(types.Part.from_bytes(
                            data=img_bytes,
                            mime_type=img_input.mime_type,
                        ))

            # Add text instruction
            user_text = request.user_instruction
            if request.context_json:
                user_text += f"\n\nContext:\n```json\n{json.dumps(request.context_json, indent=2)}\n```"
            contents.append(user_text)

            # Build generation config
            gen_config_kwargs: Dict[str, Any] = {
                "temperature": request.temperature,
                "max_output_tokens": request.max_output_tokens,
            }

            if request.system_instruction:
                gen_config_kwargs["system_instruction"] = request.system_instruction

            # Structured output via response_schema
            if request.output_schema:
                gen_config_kwargs["response_mime_type"] = "application/json"
                gen_config_kwargs["response_schema"] = request.output_schema

            from google.genai import types as gtypes
            gen_config = gtypes.GenerateContentConfig(**gen_config_kwargs)

            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=gen_config,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            # Extract text
            raw_text = response.text if response.text else ""
            if not raw_text:
                raise RetryableModelError(ModelProviderError(
                    error_code=ModelErrorCode.MODEL_EMPTY_RESPONSE,
                    provider=self.name, model_name=model_name, task_name=request.task_name,
                    retryable=True, message="Gemini returned empty response"
                ))

            # Parse JSON
            parsed = self._parse_and_validate(raw_text, request)

            # Extract usage
            usage = None
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                usage = TokenUsage(
                    input_tokens=getattr(um, "prompt_token_count", 0) or 0,
                    output_tokens=getattr(um, "candidates_token_count", 0) or 0,
                    total_tokens=getattr(um, "total_token_count", 0) or 0,
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

            # Classify error
            retryable = True
            error_code = ModelErrorCode.MODEL_PROVIDER_ERROR
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                error_code = ModelErrorCode.MODEL_RATE_LIMITED
            elif "401" in error_msg or "403" in error_msg or "PERMISSION_DENIED" in error_msg:
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

    def _resolve_image(self, img: ImageInput) -> Optional[bytes]:
        """Resolve image bytes from ImageInput."""
        if img.image_bytes:
            return img.image_bytes
        if img.storage_uri:
            from app.services.storage_service import storage_service
            try:
                return storage_service.download_from_uri(img.storage_uri)
            except Exception as e:
                logger.warning(f"Failed to download image {img.storage_uri}: {e}")
                return None
        return None

    @staticmethod
    def _strip_json_markdown_fence(raw_text: str) -> str:
        text = raw_text.strip()
        if not text.startswith("```"):
            return text
        first_nl = text.find("\n")
        if first_nl == -1:
            return text
        inner = text[first_nl + 1 :]
        if inner.rstrip().endswith("```"):
            inner = inner.rstrip()[:-3].rstrip()
        return inner.strip()

    def _parse_and_validate(self, raw_text: str, request: ModelRequest) -> Union[BaseModel, Dict[str, Any]]:
        """Parse JSON and validate against Pydantic schema. Returns the model instance when schema is set."""
        raw_text = self._strip_json_markdown_fence(raw_text)
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise RetryableModelError(ModelProviderError(
                error_code=ModelErrorCode.MODEL_INVALID_JSON,
                provider=self.name, model_name=request.model_name, task_name=request.task_name,
                retryable=True, message=f"Invalid JSON from model: {e}",
                details={"raw_text_preview": raw_text[:200]},
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
