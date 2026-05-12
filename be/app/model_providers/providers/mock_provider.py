"""
Mock Model Provider — Deterministic test provider that requires no API key.

Supports configurable modes via MOCK_MODEL_MODE:
  - success: Returns schema-compliant JSON.
  - schema_mismatch: Returns JSON missing required fields.
  - timeout: Raises a timeout error.
  - provider_error: Raises a generic provider error.
"""
from __future__ import annotations

import json
import random
from typing import Any, Dict, Optional, Type, Union, get_args, get_origin

from pydantic import BaseModel

from app.core.config import settings
from app.model_providers.base import (
    BaseModelProvider,
    ModelCallStatus,
    ModelCapability,
    ModelErrorCode,
    ModelProviderError,
    ModelRequest,
    ModelResponse,
    NonRetryableModelError,
    RetryableModelError,
    TokenUsage,
)


def _unwrap_to_basemodel(annotation: Any) -> Optional[Type[BaseModel]]:
    """If annotation is BaseModel or Optional[BaseModel], return the model class."""
    try:
        origin = get_origin(annotation)
        if origin is Union:
            for arg in get_args(annotation):
                if arg is type(None):
                    continue
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    return arg
            return None
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation
    except TypeError:
        return None
    return None


def _build_mock_output(schema_class: Optional[Type[BaseModel]]) -> Dict[str, Any]:
    """Build a minimal valid JSON output from a Pydantic model class."""
    if schema_class is None:
        return {"result": "mock_success", "message": "No schema provided"}

    data: Dict[str, Any] = {}
    for name, field_info in schema_class.model_fields.items():
        annotation = field_info.annotation

        nested = _unwrap_to_basemodel(annotation)
        if nested is not None:
            data[name] = _build_mock_output(nested)
            continue

        default = field_info.default
        try:
            from pydantic_core import PydanticUndefinedType

            has_default = not isinstance(default, PydanticUndefinedType)
        except ImportError:
            from pydantic.fields import PydanticUndefinedType  # type: ignore

            has_default = not isinstance(default, PydanticUndefinedType)

        if has_default and default is not None:
            data[name] = default
            continue

        if field_info.default_factory is not None:
            data[name] = field_info.default_factory()
            continue

        origin = getattr(annotation, "__origin__", None)
        if origin is type(None):
            data[name] = None
            continue

        args = getattr(annotation, "__args__", ())
        try:
            from typing import Literal

            if get_origin(annotation) is Literal:
                data[name] = args[0]
                continue
        except Exception:
            pass

        if origin is Union or (args and type(None) in args):
            data[name] = None
            continue

        if annotation is str or annotation == "str":
            data[name] = "mock_value"
        elif annotation is int or annotation == "int":
            data[name] = 0
        elif annotation is float or annotation == "float":
            data[name] = 0.5
        elif annotation is bool or annotation == "bool":
            data[name] = True
        elif origin is list:
            data[name] = []
        elif origin is dict:
            data[name] = {}
        else:
            data[name] = None

    return data


class MockModelProvider(BaseModelProvider):
    """Test provider — no API calls, deterministic responses."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def capabilities(self) -> set[ModelCapability]:
        return {
            ModelCapability.TEXT,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.MULTI_IMAGE,
            ModelCapability.JSON_SCHEMA,
        }

    async def generate(self, request: ModelRequest) -> ModelResponse:
        mode = settings.MOCK_MODEL_MODE
        latency_ms = random.randint(50, 200)

        base_response = ModelResponse(
            request_id=request.request_id,
            run_id=request.run_id,
            node_name=request.node_name,
            task_name=request.task_name,
            provider=self.name,
            model_name="mock-model",
            request_type=request.request_type,
            status=ModelCallStatus.SUCCESS,
            latency_ms=latency_ms,
            image_count=len(request.image_inputs),
            usage=TokenUsage(
                input_tokens=len(request.user_instruction) // 4 + 50,
                output_tokens=100,
                total_tokens=len(request.user_instruction) // 4 + 150,
            ),
        )

        if mode == "timeout":
            error = ModelProviderError(
                error_code=ModelErrorCode.MODEL_TIMEOUT,
                provider=self.name,
                model_name="mock-model",
                task_name=request.task_name,
                retryable=True,
                message="Mock timeout error",
            )
            raise RetryableModelError(error)

        if mode == "provider_error":
            error = ModelProviderError(
                error_code=ModelErrorCode.MODEL_PROVIDER_ERROR,
                provider=self.name,
                model_name="mock-model",
                task_name=request.task_name,
                retryable=False,
                message="Mock provider error",
            )
            raise NonRetryableModelError(error)

        if mode == "schema_mismatch":
            base_response.status = ModelCallStatus.SCHEMA_MISMATCH
            base_response.raw_text = '{"incomplete": true}'
            base_response.parsed_output = None
            error = ModelProviderError(
                error_code=ModelErrorCode.MODEL_SCHEMA_MISMATCH,
                provider=self.name,
                model_name="mock-model",
                task_name=request.task_name,
                retryable=True,
                message="Mock schema mismatch",
            )
            raise RetryableModelError(error)

        output = _build_mock_output(request.output_schema)
        if request.output_schema:
            base_response.parsed_output = request.output_schema.model_validate(output)
            base_response.raw_text = base_response.parsed_output.model_dump_json()
        else:
            base_response.parsed_output = output
            base_response.raw_text = json.dumps(output)
        return base_response
