"""
Retry, Timeout & Fallback Handler — wraps provider.generate() with resilience.

Rules per user decision:
  - Retry: timeout, rate_limit, 5xx, invalid JSON, schema mismatch (RetryableModelError),
    unless DISABLE_MODEL_CALL_ASYNCIO_TIMEOUT skips asyncio-level timeouts.
  - No retry: auth, config, capability errors (NonRetryableModelError).
  - Fallback: if primary exhausts retries AND ENABLE_MODEL_FALLBACK=true.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Optional

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    RetryError,
)

from app.core.config import settings
from app.core.logging import log_event, logger
from app.model_providers.base import (
    BaseModelProvider,
    ModelCallStatus,
    ModelErrorCode,
    ModelProviderError,
    ModelRequest,
    ModelResponse,
    NonRetryableModelError,
    RetryableModelError,
)


def _same_provider_fallback_model(task_name: str) -> str:
    """Alternate model on the primary provider when the spec names a same-provider fallback."""
    if task_name == "screen_intent_extraction":
        return settings.SCREEN_INTENT_FALLBACK_MODEL_NAME or ""
    if task_name in ("llm_flow_discovery", "intent_aware_flow_discovery"):
        return settings.FLOW_DISCOVERY_FALLBACK_MODEL_NAME or ""
    if task_name == "scenario_evidence_audit":
        return settings.SCENARIO_VALIDATION_FALLBACK_MODEL_NAME or ""
    return ""


def _cross_provider_fallback_model(task_name: str, fallback_provider_name: str) -> str:
    if task_name == "ui_state_extraction" and fallback_provider_name == settings.UI_STATE_EXTRACTION_FALLBACK_PROVIDER:
        return settings.UI_STATE_EXTRACTION_FALLBACK_MODEL_NAME or ""
    if (
        task_name == "joint_screen_understanding"
        and fallback_provider_name == settings.JOINT_SCREEN_UNDERSTANDING_FALLBACK_PROVIDER
    ):
        return settings.JOINT_SCREEN_UNDERSTANDING_FALLBACK_MODEL_NAME or ""
    return ""


async def execute_with_retry(
    provider: BaseModelProvider,
    request: ModelRequest,
    fallback_provider: Optional[BaseModelProvider] = None,
) -> ModelResponse:
    """
    Execute provider.generate() with retry/timeout/fallback logic.
    Returns ModelResponse. Raises NonRetryableModelError if all attempts fail.
    """
    retry_count = 0

    use_asyncio_deadline = not settings.DISABLE_MODEL_CALL_ASYNCIO_TIMEOUT
    if getattr(request, "timeout_seconds", None) is not None and request.timeout_seconds <= 0:
        use_asyncio_deadline = False

    timeout_secs = 60
    if use_asyncio_deadline:
        if getattr(request, "timeout_seconds", None) and request.timeout_seconds > 0:
            timeout_secs = request.timeout_seconds
        elif request.image_inputs:
            timeout_secs = settings.VISION_MODEL_TIMEOUT_SECONDS
        else:
            timeout_secs = settings.TEXT_MODEL_TIMEOUT_SECONDS

    async def _attempt(p: BaseModelProvider, req: ModelRequest) -> ModelResponse:
        """Single attempt; optional asyncio deadline around provider.generate()."""
        if not use_asyncio_deadline:
            return await p.generate(req)
        try:
            return await asyncio.wait_for(p.generate(req), timeout=timeout_secs)
        except asyncio.TimeoutError:
            raise RetryableModelError(ModelProviderError(
                error_code=ModelErrorCode.MODEL_TIMEOUT,
                provider=p.name,
                model_name=req.model_name or "",
                task_name=req.task_name,
                retryable=True,
                message=f"Model call timed out after {timeout_secs}s",
            ))

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(RetryableModelError),
            stop=stop_after_attempt(settings.MODEL_MAX_RETRIES + 1),
            wait=wait_exponential(
                multiplier=settings.MODEL_RETRY_BACKOFF_SECONDS,
                min=settings.MODEL_RETRY_BACKOFF_SECONDS,
                max=settings.MODEL_RETRY_BACKOFF_SECONDS * 8,
            ),
            reraise=True,
        ):
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    retry_count = attempt.retry_state.attempt_number - 1
                    log_event(
                        "model_call_retried",
                        run_id=request.run_id,
                        node_name=request.node_name,
                        task_name=request.task_name,
                        provider=provider.name,
                        retry_count=retry_count,
                    )
                response = await _attempt(provider, request)
                response.retry_count = retry_count
                return response

    except (RetryableModelError, NonRetryableModelError) as primary_err:
        error = primary_err.error if hasattr(primary_err, "error") else None

        if settings.ENABLE_MODEL_FALLBACK:
            alt_model = _same_provider_fallback_model(request.task_name)
            cur_model = request.model_name or ""
            if alt_model and alt_model != cur_model:
                try:
                    logger.warning(
                        f"Primary model '{cur_model or 'default'}' failed for task '{request.task_name}', "
                        f"retrying same provider '{provider.name}' with '{alt_model}'"
                    )
                    log_event(
                        "model_same_provider_fallback_used",
                        run_id=request.run_id,
                        node_name=request.node_name,
                        task_name=request.task_name,
                        provider=provider.name,
                        alternate_model=alt_model,
                    )
                    response = await _attempt(provider, replace(request, model_name=alt_model))
                    response.retry_count = retry_count
                    return response
                except Exception:
                    pass

        # Try fallback if enabled and available
        if settings.ENABLE_MODEL_FALLBACK and fallback_provider is not None:
            logger.warning(
                f"Primary provider '{provider.name}' failed for task '{request.task_name}', "
                f"trying fallback '{fallback_provider.name}'"
            )
            log_event(
                "model_fallback_used",
                run_id=request.run_id,
                node_name=request.node_name,
                task_name=request.task_name,
                primary_provider=provider.name,
                fallback_provider=fallback_provider.name,
            )
            try:
                fb_model = _cross_provider_fallback_model(request.task_name, fallback_provider.name)
                fb_request = replace(request, model_name=fb_model) if fb_model else request
                response = await _attempt(fallback_provider, fb_request)
                response.retry_count = retry_count
                return response
            except Exception as fallback_err:
                raise NonRetryableModelError(ModelProviderError(
                    error_code=ModelErrorCode.MODEL_FALLBACK_FAILED,
                    provider=fallback_provider.name,
                    model_name=request.model_name or "",
                    task_name=request.task_name,
                    retryable=False,
                    message=f"Both primary ({provider.name}) and fallback ({fallback_provider.name}) failed. "
                            f"Last error: {fallback_err}",
                )) from fallback_err

        # Re-raise the original error as NonRetryable (retries exhausted)
        if error:
            raise NonRetryableModelError(ModelProviderError(
                error_code=error.error_code,
                provider=error.provider,
                model_name=error.model_name,
                task_name=error.task_name,
                retryable=False,
                message=f"All {settings.MODEL_MAX_RETRIES + 1} attempts failed. Last: {error.message}",
                details=error.details,
            ))
        raise

    except RetryError as e:
        raise NonRetryableModelError(ModelProviderError(
            error_code=ModelErrorCode.MODEL_PROVIDER_ERROR,
            provider=provider.name,
            model_name=request.model_name or "",
            task_name=request.task_name,
            retryable=False,
            message=f"Retry exhausted: {e}",
        )) from e
