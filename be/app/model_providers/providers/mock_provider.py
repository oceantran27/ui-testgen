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
import time
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from app.core.config import settings
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


def _generate_default_value(field_type: Any) -> Any:
    """Generate a minimal valid value for common Pydantic field types."""
    origin = getattr(field_type, "__origin__", None)
    if origin is list:
        return []
    if origin is dict:
        return {}
    if field_type is str:
        return "mock_value"
    if field_type is int:
        return 0
    if field_type is float:
        return 0.5
    if field_type is bool:
        return True
    return None


def _build_mock_output(schema_class: Optional[Type[BaseModel]]) -> Dict[str, Any]:
    """Build a minimal valid JSON output from a Pydantic model class."""
    if schema_class is None:
        return {"result": "mock_success", "message": "No schema provided"}

    data: Dict[str, Any] = {}
    for name, field_info in schema_class.model_fields.items():
        annotation = field_info.annotation

        # Use default if available and not PydanticUndefined
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

        # Generate from type annotation
        origin = getattr(annotation, "__origin__", None)
        # Handle Optional[X] → extract inner type
        if origin is type(None):
            data[name] = None
            continue

        args = getattr(annotation, "__args__", ())
        # Literal → take first value
        try:
            from typing import Literal, get_origin
            if get_origin(annotation) is Literal:
                data[name] = args[0]
                continue
        except Exception:
            pass

        # Optional[X] has NoneType as one of args
        if origin is type(None) or (args and type(None) in args):
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
        start = time.time()

        # Simulate latency
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

        # success mode
        output = _build_mock_output(request.output_schema)
        if request.output_schema:
            base_response.parsed_output = request.output_schema.model_validate(output)
            base_response.raw_text = base_response.parsed_output.model_dump_json()
        else:
            base_response.parsed_output = output
            base_response.raw_text = json.dumps(output)
        return base_response
