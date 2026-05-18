"""
Model Provider Base — Core abstractions for vendor-agnostic LLM/VLM calls.

Defines:
  - Enums for capability, request type, and call status.
  - Dataclasses for ModelRequest, ModelResponse, ImageInput, TokenUsage, ModelProviderError.
  - ABC BaseModelProvider that all providers must implement.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class ModelCapability(str, Enum):
    TEXT = "text"
    VISION = "vision"
    STRUCTURED_OUTPUT = "structured_output"
    MULTI_IMAGE = "multi_image"
    JSON_SCHEMA = "json_schema"


class RequestType(str, Enum):
    TEXT_STRUCTURED = "text_structured"
    VISION_STRUCTURED = "vision_structured"
    PAIRWISE_VISION = "pairwise_vision"
    MULTI_IMAGE_REASONING = "multi_image_reasoning"


class ModelCallStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RETRIED = "retried"
    TIMEOUT = "timeout"
    SCHEMA_MISMATCH = "schema_mismatch"


# ──────────────────────────────────────────────
# Error codes (from spec Module 5.11)
# ──────────────────────────────────────────────

class ModelErrorCode(str, Enum):
    MODEL_PROVIDER_NOT_FOUND = "MODEL_PROVIDER_NOT_FOUND"
    MODEL_CAPABILITY_NOT_SUPPORTED = "MODEL_CAPABILITY_NOT_SUPPORTED"
    MODEL_AUTH_FAILED = "MODEL_AUTH_FAILED"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_INVALID_REQUEST = "MODEL_INVALID_REQUEST"
    MODEL_EMPTY_RESPONSE = "MODEL_EMPTY_RESPONSE"
    MODEL_INVALID_JSON = "MODEL_INVALID_JSON"
    MODEL_SCHEMA_MISMATCH = "MODEL_SCHEMA_MISMATCH"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    MODEL_FALLBACK_FAILED = "MODEL_FALLBACK_FAILED"
    MODEL_OUTPUT_REJECTED = "MODEL_OUTPUT_REJECTED"


# ──────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────

@dataclass
class ImageInput:
    """Represents an image to send to a model."""
    image_id: Optional[str] = None
    storage_uri: Optional[str] = None
    image_bytes: Optional[bytes] = None
    mime_type: str = "image/png"


@dataclass
class TokenUsage:
    """Token usage metadata returned by a provider."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ModelProviderError:
    """Standardized error from any model provider."""
    error_code: str  # from ModelErrorCode
    provider: str
    model_name: str
    task_name: str
    retryable: bool
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class ModelRequest:
    """Vendor-agnostic model request."""
    task_name: str
    run_id: str
    node_name: str
    request_type: RequestType

    system_instruction: str = ""
    user_instruction: str = ""
    context_json: Optional[Dict[str, Any]] = None
    image_inputs: List[ImageInput] = field(default_factory=list)

    # Pydantic model class for structured output validation
    output_schema: Optional[Type[BaseModel]] = None

    # Provider routing (resolved by registry if empty)
    provider: str = ""
    model_name: str = ""

    # Generation params
    temperature: float = 0
    max_output_tokens: int = 4096
    timeout_seconds: int = 60

    # Auto-generated
    request_id: str = field(default_factory=lambda: f"mcall_{uuid.uuid4().hex[:12]}")


@dataclass
class ModelResponse:
    """Normalized response from any model provider."""
    request_id: str
    run_id: str
    node_name: str
    task_name: str
    provider: str
    model_name: str
    request_type: RequestType
    status: ModelCallStatus

    parsed_output: Optional[Any] = None
    raw_text: Optional[str] = None
    usage: Optional[TokenUsage] = None
    latency_ms: int = 0
    retry_count: int = 0
    image_count: int = 0
    error: Optional[ModelProviderError] = None


# ──────────────────────────────────────────────
# Retryable error (used by retry_handler)
# ──────────────────────────────────────────────

class RetryableModelError(Exception):
    """Raised by providers when the error is retryable."""
    def __init__(self, error: ModelProviderError):
        self.error = error
        super().__init__(error.message)


class NonRetryableModelError(Exception):
    """Raised by providers when the error is NOT retryable."""
    def __init__(self, error: ModelProviderError):
        self.error = error
        super().__init__(error.message)


# ──────────────────────────────────────────────
# Abstract Base Provider
# ──────────────────────────────────────────────

class BaseModelProvider(ABC):
    """
    Abstract base class for all model providers.
    Each provider (Gemini, OpenAI, Mock) must implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name, e.g. 'gemini', 'openai', 'mock'."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> set[ModelCapability]:
        """Set of capabilities this provider supports."""
        ...

    def supports(self, capability: ModelCapability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """
        Execute a model call. Must return a ModelResponse.
        Should raise RetryableModelError or NonRetryableModelError on failure.
        """
        ...
