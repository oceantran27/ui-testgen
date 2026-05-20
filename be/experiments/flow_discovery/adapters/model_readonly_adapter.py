"""Model adapter for flow_discovery experiments — no orchestration / DB persistence."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.config import settings
from app.model_providers import model_adapter
from app.model_providers.base import ModelCallStatus
from app.model_providers.schemas import GlobalFlowDiscoveryResult

from experiments.flow_discovery import config


def model_config_snapshot() -> Dict[str, Any]:
    return {
        "flow_discovery_provider": getattr(settings, "FLOW_DISCOVERY_MODEL_PROVIDER", None),
        "flow_discovery_model_name": getattr(settings, "FLOW_DISCOVERY_MODEL_NAME", None),
        "global_flow_discovery_max_output_tokens": getattr(settings, "GLOBAL_FLOW_DISCOVERY_MAX_OUTPUT_TOKENS", None),
        "global_flow_discovery_max_screens": getattr(settings, "GLOBAL_FLOW_DISCOVERY_MAX_SCREENS", None),
    }


async def call_global_flow_discovery_llm(
    *,
    run_id: str,
    system_instruction: str,
    user_instruction: str,
    prompt_name: Optional[str] = None,
    prompt_version: Optional[str] = None,
    provider_override: Optional[str] = None,
    model_name_override: Optional[str] = None,
    node_name: Optional[str] = None,
):
    """Parallel to ``global_flow_discovery_service.run_global_flow_discovery`` LLM block only."""

    pname = prompt_name or config.PROMPT_NAME
    pver = prompt_version or config.PROMPT_VERSION
    prov = (
        provider_override if provider_override is not None else settings.FLOW_DISCOVERY_MODEL_PROVIDER
    )
    mname = model_name_override if model_name_override is not None else settings.FLOW_DISCOVERY_MODEL_NAME

    return await model_adapter.call_text_structured(
        task_name="global_flow_discovery",
        run_id=run_id,
        node_name=node_name or config.DEFAULT_NODE_NAME_RAW_CAPTURE,
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        output_schema=GlobalFlowDiscoveryResult,
        prompt_name=pname,
        prompt_version=pver,
        provider_override=prov,
        model_name_override=mname,
    )


def empty_global_flow_discovery_shell() -> Dict[str, Any]:
    return GlobalFlowDiscoveryResult.model_validate({}).model_dump(mode="json")


def normalize_global_flow_discovery_llm_response(resp: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Produce ``raw_model_output`` JSON plus diagnostics merged later into validation_metrics.

    Works with lightweight ``ModelResponse``-compatible stubs used in tests.
    """

    diag: Dict[str, Any] = {
        "llm_status": getattr(getattr(resp, "status", None), "value", str(getattr(resp, "status", ""))),
        "llm_provider": getattr(resp, "provider", ""),
        "llm_model_name": getattr(resp, "model_name", ""),
        "latency_ms": getattr(resp, "latency_ms", 0),
    }

    status_val = getattr(resp.status, "value", str(resp.status))
    parsed = getattr(resp, "parsed_output", None)

    if status_val == ModelCallStatus.SUCCESS.value and parsed is not None:
        raw_dict: Dict[str, Any]
        if hasattr(parsed, "model_dump"):
            raw_dict = parsed.model_dump(mode="json")
        elif isinstance(parsed, dict):
            raw_dict = dict(parsed)
        else:
            raw_dict = GlobalFlowDiscoveryResult.model_validate(parsed).model_dump(mode="json")
        return raw_dict, diag

    err_obj = getattr(resp, "error", None)
    err_msg = getattr(err_obj, "message", None) if err_obj is not None else None
    diag["llm_error"] = err_msg or str(err_obj or "LLM_FAILED")
    diag["failure"] = True
    return empty_global_flow_discovery_shell(), diag
