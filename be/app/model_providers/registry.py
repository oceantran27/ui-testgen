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
from app.core.prompt_manager import prompt_manager
from app.model_providers.db_session_context import model_call_db_session, model_call_job_id

try:
    from app.core import pipeline_run_log as _prl
except ImportError:  # pragma: no cover
    _prl = None  # type: ignore


def _serialize_model_request_for_log(req: ModelRequest) -> Dict[str, Any]:
    imgs = []
    for ii in req.image_inputs or []:
        imgs.append({
            "image_id": ii.image_id,
            "storage_uri": ii.storage_uri,
            "mime_type": ii.mime_type,
            "image_base64_len": len(ii.image_bytes) if ii.image_bytes else 0,
        })
    return {
        "request_id": req.request_id,
        "task_name": req.task_name,
        "run_id": req.run_id,
        "node_name": req.node_name,
        "request_type": req.request_type.value if hasattr(req.request_type, "value") else str(req.request_type),
        "system_instruction": req.system_instruction,
        "user_instruction": req.user_instruction,
        "context_json": req.context_json,
        "image_inputs": imgs,
        "output_schema": req.output_schema.__name__ if req.output_schema else None,
        "provider": req.provider,
        "model_name": req.model_name,
        "temperature": req.temperature,
        "max_output_tokens": req.max_output_tokens,
        "timeout_seconds": req.timeout_seconds,
    }


def _serialize_model_response_for_log(resp: ModelResponse) -> Dict[str, Any]:
    err = None
    if resp.error:
        ec = resp.error.error_code
        if hasattr(ec, "value"):
            ec = ec.value
        err = {
            "error_code": ec,
            "message": resp.error.message,
            "provider": resp.error.provider,
            "model_name": resp.error.model_name,
            "task_name": resp.error.task_name,
        }
    usage = None
    if resp.usage:
        usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "total_tokens": resp.usage.total_tokens,
        }
    po = resp.parsed_output
    if po is not None and hasattr(po, "model_dump"):
        po = po.model_dump()
    return {
        "request_id": resp.request_id,
        "status": resp.status.value if hasattr(resp.status, "value") else str(resp.status),
        "provider": resp.provider,
        "model_name": resp.model_name,
        "task_name": resp.task_name,
        "raw_text": resp.raw_text,
        "parsed_output": po,
        "latency_ms": resp.latency_ms,
        "retry_count": resp.retry_count,
        "image_count": resp.image_count,
        "usage": usage,
        "error": err,
    }


async def _execute_with_retry_pipeline_log(
    provider: BaseModelProvider,
    request: ModelRequest,
    fallback: Optional[BaseModelProvider],
) -> ModelResponse:
    """Same as execute_with_retry; when pipeline_run_log is active, writes raw request+response to file only."""
    active = _prl is not None and _prl.is_active()
    try:
        response = await execute_with_retry(provider, request, fallback)
    except Exception as e:
        if active:
            payload = {
                "request": _serialize_model_request_for_log(request),
                "error": str(e),
            }
            path = _prl.write_raw_json(f"model_{request.task_name}_error", payload)
            _prl.file_detail(
                f"model:{request.task_name}",
                [f"request_id={request.request_id}", "call_failed", str(e)[:200]],
                raw_path=path,
            )
        raise
    if active:
        payload = {
            "request": _serialize_model_request_for_log(request),
            "response": _serialize_model_response_for_log(response),
        }
        path = _prl.write_raw_json(f"model_{request.task_name}", payload)
        _prl.file_detail(
            f"model:{request.task_name}",
            [
                f"request_id={request.request_id}",
                f"node={request.node_name}",
                f"status={response.status.value}",
            ],
            raw_path=path,
        )
    db_sess = model_call_db_session.get()
    if db_sess is not None:
        from app.model_providers.usage_logger import log_model_call

        try:
            await log_model_call(
                db_sess, response, job_id=model_call_job_id.get()
            )
        except Exception as log_exc:
            logger.warning("log_model_call failed for %s: %s", request.request_id, log_exc)
    return response


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

        max_output_tokens = 4096
        if task_name in ("llm_flow_discovery", "intent_aware_flow_discovery", "global_flow_discovery"):
            max_output_tokens = (
                settings.GLOBAL_FLOW_DISCOVERY_MAX_OUTPUT_TOKENS
                if task_name == "global_flow_discovery"
                else settings.FLOW_DISCOVERY_MAX_OUTPUT_TOKENS
            )
        elif task_name == "screen_intent_extraction":
            max_output_tokens = settings.SCREEN_INTENT_MAX_OUTPUT_TOKENS
        elif task_name == "behaviour_contract_builder":
            max_output_tokens = settings.BEHAVIOUR_CONTRACT_BUILDER_MAX_OUTPUT_TOKENS
        elif task_name == "bdd_scenario_generation":
            max_output_tokens = settings.BDD_SCENARIO_GENERATION_MAX_OUTPUT_TOKENS
        elif task_name == "scenario_evidence_audit":
            max_output_tokens = settings.SCENARIO_EVIDENCE_AUDIT_MAX_OUTPUT_TOKENS

        timeout_seconds = settings.TEXT_MODEL_TIMEOUT_SECONDS
        if task_name == "scenario_evidence_audit":
            timeout_seconds = settings.SCENARIO_EVIDENCE_AUDIT_TIMEOUT_SECONDS

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
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )

        return await _execute_with_retry_pipeline_log(provider, request, fallback)

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
        vision_timeout_secs = settings.VISION_MODEL_TIMEOUT_SECONDS
        if task_name == "ui_state_extraction":
            max_output_tokens = settings.UI_STATE_EXTRACTION_MAX_OUTPUT_TOKENS
            vision_timeout_secs = settings.UI_STATE_EXTRACTION_TIMEOUT_SECONDS
        elif task_name == "joint_screen_understanding":
            max_output_tokens = settings.JOINT_SCREEN_UNDERSTANDING_MAX_OUTPUT_TOKENS
            vision_timeout_secs = settings.JOINT_SCREEN_UNDERSTANDING_TIMEOUT_SECONDS

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
            timeout_seconds=vision_timeout_secs,
        )

        return await _execute_with_retry_pipeline_log(provider, request, fallback)




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
    if (
        settings.GEMINI_API_KEY
        or settings.DEFAULT_MODEL_PROVIDER == "gemini"
        or settings.UI_STATE_EXTRACTION_PROVIDER == "gemini"
        or settings.UI_STATE_EXTRACTION_FALLBACK_PROVIDER == "gemini"
    ):
        registry.register(GeminiModelProvider())

    # Register OpenAI if default/fallback or key present (lazy auth at call time)
    if (
        settings.OPENAI_API_KEY
        or settings.FALLBACK_MODEL_PROVIDER == "openai"
        or settings.DEFAULT_MODEL_PROVIDER == "openai"
    ):
        registry.register(OpenAIModelProvider())

    return registry


# Module-level singletons
_registry = _create_registry()
model_adapter = ModelProviderAdapter(_registry)
