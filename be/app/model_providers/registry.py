"""
Provider Registry & ModelProviderAdapter Facade.

Registry: maps provider name → BaseModelProvider instance (singleton per provider).
ModelProviderAdapter: the single entry point for all nodes to call models.
  Keeps prompt metadata (prompt_name, prompt_version) for future extraction into PromptTemplateManager.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import log_event, logger
from app.model_providers.base import (
    BaseModelProvider,
    ImageInput,
    ModelCapability,
    ModelErrorCode,
    ModelProviderError,
    ModelRequest,
    ModelResponse,
    NonRetryableModelError,
    RequestType,
)
from app.model_providers.retry_handler import execute_with_retry


# ──────────────────────────────────────────────
# Provider Registry
# ──────────────────────────────────────────────

class ProviderRegistry:
    """Singleton registry for model provider instances."""

    _instance: Optional["ProviderRegistry"] = None
    _providers: Dict[str, BaseModelProvider] = {}

    @classmethod
    def instance(cls) -> "ProviderRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, provider: BaseModelProvider) -> None:
        self._providers[provider.name] = provider
        logger.info(f"Model provider registered: {provider.name}")

    def get(self, name: str) -> BaseModelProvider:
        if name not in self._providers:
            raise NonRetryableModelError(ModelProviderError(
                error_code=ModelErrorCode.MODEL_PROVIDER_NOT_FOUND,
                provider=name,
                model_name="",
                task_name="",
                retryable=False,
                message=f"Provider '{name}' not found. Available: {list(self._providers.keys())}",
            ))
        return self._providers[name]

    def get_for_task(self, task_name: str) -> BaseModelProvider:
        """
        Resolve provider for a task.
        Priority: task-specific env var → DEFAULT_MODEL_PROVIDER → first registered.
        """
        # Could be extended later with per-task env config (e.g. UI_STATE_EXTRACTION_PROVIDER)
        provider_name = settings.DEFAULT_MODEL_PROVIDER
        return self.get(provider_name)

    def get_fallback(self, primary_name: str) -> Optional[BaseModelProvider]:
        """Return fallback provider if configured and different from primary."""
        if not settings.ENABLE_MODEL_FALLBACK:
            return None
        fallback_name = settings.FALLBACK_MODEL_PROVIDER
        if fallback_name == primary_name or fallback_name not in self._providers:
            return None
        return self._providers[fallback_name]

    def all_providers(self) -> List[str]:
        return list(self._providers.keys())


# ──────────────────────────────────────────────
# Adapter Facade — single entry point for nodes
# ──────────────────────────────────────────────

class ModelProviderAdapter:
    """
    Facade for all model calls from LangGraph nodes.
    Keeps prompt_name and prompt_version as metadata on each call,
    so the adapter can be refactored into a PromptTemplateManager at Phase 7+.
    """

    def __init__(self, registry: ProviderRegistry):
        self._registry = registry

    def _resolve_provider_and_fallback(
        self,
        task_name: str,
        required_capability: Optional[ModelCapability] = None,
    ):
        provider = self._registry.get_for_task(task_name)

        # Validate capability
        if required_capability and not provider.supports(required_capability):
            raise NonRetryableModelError(ModelProviderError(
                error_code=ModelErrorCode.MODEL_CAPABILITY_NOT_SUPPORTED,
                provider=provider.name,
                model_name="",
                task_name=task_name,
                retryable=False,
                message=f"Provider '{provider.name}' does not support capability '{required_capability}'.",
            ))

        fallback = self._registry.get_fallback(provider.name)
        return provider, fallback

    async def call_text_structured(
        self,
        *,
        task_name: str,
        run_id: str,
        node_name: str,
        system_instruction: str,
        user_instruction: str,
        output_schema: Type[BaseModel],
        context_json: Optional[Dict[str, Any]] = None,
        prompt_name: str = "",
        prompt_version: str = "v1",
        provider_override: str = "",
        model_name_override: str = "",
        temperature: float = 0.2,
    ) -> ModelResponse:
        """
        Structured text call. Returns ModelResponse with parsed_output validated against output_schema.
        """
        log_event(
            "model_call_started",
            run_id=run_id,
            node_name=node_name,
            task_name=task_name,
            request_type=RequestType.TEXT_STRUCTURED,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )

        provider, fallback = self._resolve_provider_and_fallback(
            task_name, required_capability=ModelCapability.STRUCTURED_OUTPUT
        )
        if provider_override:
            provider = self._registry.get(provider_override)
            fallback = self._registry.get_fallback(provider.name)

        request = ModelRequest(
            task_name=task_name,
            run_id=run_id,
            node_name=node_name,
            request_type=RequestType.TEXT_STRUCTURED,
            system_instruction=system_instruction,
            user_instruction=user_instruction,
            context_json=context_json,
            output_schema=output_schema,
            provider=provider.name,
            model_name=model_name_override,
            temperature=temperature,
            timeout_seconds=settings.TEXT_MODEL_TIMEOUT_SECONDS,
        )

        return await execute_with_retry(provider, request, fallback)

    async def call_vision_structured(
        self,
        *,
        task_name: str,
        run_id: str,
        node_name: str,
        system_instruction: str,
        user_instruction: str,
        image_inputs: List[ImageInput],
        output_schema: Type[BaseModel],
        context_json: Optional[Dict[str, Any]] = None,
        prompt_name: str = "",
        prompt_version: str = "v1",
        provider_override: str = "",
        model_name_override: str = "",
        temperature: float = 0.2,
    ) -> ModelResponse:
        """
        Structured vision call. Accepts 1 or more images.
        """
        log_event(
            "model_call_started",
            run_id=run_id,
            node_name=node_name,
            task_name=task_name,
            request_type=RequestType.VISION_STRUCTURED,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            image_count=len(image_inputs),
        )

        provider, fallback = self._resolve_provider_and_fallback(
            task_name, required_capability=ModelCapability.VISION
        )
        if provider_override:
            provider = self._registry.get(provider_override)
            fallback = self._registry.get_fallback(provider.name)

        max_output_tokens = 4096
        if task_name == "ui_state_extraction":
            max_output_tokens = settings.UI_STATE_EXTRACTION_MAX_OUTPUT_TOKENS

        request = ModelRequest(
            task_name=task_name,
            run_id=run_id,
            node_name=node_name,
            request_type=RequestType.VISION_STRUCTURED,
            system_instruction=system_instruction,
            user_instruction=user_instruction,
            image_inputs=image_inputs,
            context_json=context_json,
            output_schema=output_schema,
            provider=provider.name,
            model_name=model_name_override,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            timeout_seconds=settings.VISION_MODEL_TIMEOUT_SECONDS,
        )

        return await execute_with_retry(provider, request, fallback)

    async def call_pairwise_vision(
        self,
        *,
        task_name: str,
        run_id: str,
        node_name: str,
        instruction: str,
        image_a: ImageInput,
        image_b: ImageInput,
        output_schema: Type[BaseModel],
        prompt_name: str = "",
        prompt_version: str = "v1",
        provider_override: str = "",
    ) -> ModelResponse:
        """
        Pairwise vision comparison call. Sends exactly 2 images.
        Used for: semantic duplicate verification, pairwise state comparison.
        """
        log_event(
            "model_call_started",
            run_id=run_id,
            node_name=node_name,
            task_name=task_name,
            request_type=RequestType.PAIRWISE_VISION,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )

        provider, fallback = self._resolve_provider_and_fallback(
            task_name, required_capability=ModelCapability.VISION
        )
        if provider_override:
            provider = self._registry.get(provider_override)
            fallback = self._registry.get_fallback(provider.name)

        request = ModelRequest(
            task_name=task_name,
            run_id=run_id,
            node_name=node_name,
            request_type=RequestType.PAIRWISE_VISION,
            system_instruction="You are a UI state comparison expert. Compare the two screenshots provided.",
            user_instruction=instruction,
            image_inputs=[image_a, image_b],
            output_schema=output_schema,
            provider=provider.name,
            timeout_seconds=settings.VISION_MODEL_TIMEOUT_SECONDS,
        )

        return await execute_with_retry(provider, request, fallback)


# ──────────────────────────────────────────────
# Bootstrap & Singleton Initialization
# ──────────────────────────────────────────────

def _create_registry() -> ProviderRegistry:
    """Initialize and populate the provider registry from config."""
    from app.model_providers.providers.mock_provider import MockModelProvider
    from app.model_providers.providers.gemini_provider import GeminiModelProvider
    from app.model_providers.providers.openai_provider import OpenAIModelProvider

    registry = ProviderRegistry.instance()

    # Always register mock (no API key needed)
    registry.register(MockModelProvider())

    # Register Gemini if key available
    if settings.GEMINI_API_KEY or settings.DEFAULT_MODEL_PROVIDER == "gemini":
        registry.register(GeminiModelProvider())

    # Register OpenAI if key available
    if settings.OPENAI_API_KEY or settings.FALLBACK_MODEL_PROVIDER == "openai":
        registry.register(OpenAIModelProvider())

    return registry


# Module-level singletons
_registry = _create_registry()
model_adapter = ModelProviderAdapter(_registry)
