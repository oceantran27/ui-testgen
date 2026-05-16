"""
Model Providers Package — Phase 5 LLM/VLM infrastructure.

Public API:
    model_adapter   — ModelProviderAdapter singleton (use this in LangGraph nodes)
    model_adapter.call_text_structured(...)
    model_adapter.call_vision_structured(...)
    model_adapter.call_pairwise_vision(...)

    log_model_call  — persist ModelResponse to DB
"""
from app.model_providers.registry import model_adapter, ModelProviderAdapter, ProviderRegistry
from app.model_providers.usage_logger import log_model_call
from app.model_providers.base import (
    ModelRequest,
    ModelResponse,
    ImageInput,
    TokenUsage,
    ModelProviderError,
    ModelCapability,
    RequestType,
    ModelCallStatus,
    ModelErrorCode,
    RetryableModelError,
    NonRetryableModelError,
    BaseModelProvider,
)

__all__ = [
    "model_adapter",
    "ModelProviderAdapter",
    "ProviderRegistry",
    "log_model_call",
    "ModelRequest",
    "ModelResponse",
    "ImageInput",
    "TokenUsage",
    "ModelProviderError",
    "ModelCapability",
    "RequestType",
    "ModelCallStatus",
    "ModelErrorCode",
    "RetryableModelError",
    "NonRetryableModelError",
    "BaseModelProvider",
]
