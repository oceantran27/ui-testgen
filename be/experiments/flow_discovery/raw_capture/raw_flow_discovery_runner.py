"""Experiment runner: compressed catalog JSON → LLM → RawFlowDiscoveryExperimentPackage."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Dict, Optional

from experiments.flow_discovery import config
from experiments.flow_discovery.adapters import (
    model_readonly_adapter,
    prompt_readonly_adapter,
    system_readonly_adapter,
)
from experiments.flow_discovery.io_utils import utc_now_iso
from experiments.flow_discovery.raw_capture import input_bundle_builder, raw_output_normalizer
from experiments.flow_discovery.raw_capture import raw_output_writer
from experiments.flow_discovery.schemas.raw_output_schema import RawFlowDiscoveryExperimentPackage

ModelCaller = Callable[..., Awaitable[Any]]


async def default_model_caller(**kwargs: Any) -> Any:
    return await model_readonly_adapter.call_global_flow_discovery_llm(**kwargs)


class ExperimentRawFlowDiscoveryRunner:
    """
    Production-parity LLM call without ``run_global_flow_discovery`` orchestration/persist.

    ``model_caller`` is injectable for tests (fake ``ModelResponse``).
    """

    def __init__(
        self,
        *,
        model_caller: Optional[ModelCaller] = None,
        validate_screen_count: bool = True,
    ) -> None:
        self._model_caller = model_caller or default_model_caller
        self._validate_screen_count = validate_screen_count

    async def run_from_compressed_catalog(
        self,
        app_id: str,
        compressed_catalog_path: Path | str,
        *,
        run_id: Optional[str] = None,
        prompt_version: Optional[str] = None,
        provider_override: Optional[str] = None,
        model_name_override: Optional[str] = None,
        prompt_name_override: Optional[str] = None,
        max_catalog_screens: Optional[int] = None,
        write_to_path: Optional[Path | str] = None,
    ) -> RawFlowDiscoveryExperimentPackage:
        rid = run_id or f"experiment_{uuid.uuid4().hex[:12]}"

        bundle = input_bundle_builder.build_discovery_input_bundle(
            compressed_catalog_path,
            validate_screen_count=self._validate_screen_count,
            max_screens=max_catalog_screens,
        )

        system_instruction = prompt_readonly_adapter.get_global_flow_discovery_prompt()
        user_instruction = prompt_readonly_adapter.build_flow_discovery_user_instruction(
            bundle.llm_discovery_catalog
        )

        prompt_snap = prompt_readonly_adapter.prompt_snapshot(preview_chars=200)
        if prompt_version:
            prompt_snap = {**prompt_snap, "prompt_version": prompt_version}

        cfg_snap = model_readonly_adapter.model_config_snapshot()
        if prompt_version:
            cfg_snap = {**cfg_snap, "prompt_version_effective": prompt_version}
        if provider_override:
            cfg_snap = {**cfg_snap, "provider_override": provider_override}
        if model_name_override:
            cfg_snap = {**cfg_snap, "model_name_override": model_name_override}

        resp = await self._model_caller(
            run_id=rid,
            system_instruction=system_instruction,
            user_instruction=user_instruction,
            prompt_name=prompt_name_override or config.PROMPT_NAME,
            prompt_version=prompt_version or config.PROMPT_VERSION,
            provider_override=provider_override,
            model_name_override=model_name_override,
            node_name=config.DEFAULT_NODE_NAME_RAW_CAPTURE,
        )

        raw_model_output, llm_diag = raw_output_normalizer.normalize_llm_discovery_response(resp)

        repaired_output: Optional[Dict[str, Any]]
        warnings: list[str]
        metrics: Dict[str, Any]

        if llm_diag.get("failure"):
            repaired_output = None
            err = str(llm_diag.get("llm_error") or "LLM_FAILED")
            warnings = [f"LLM_FAILED:{err}"]
            metrics = dict(llm_diag)
        else:
            repaired_output, warnings, metrics = system_readonly_adapter.build_validation_snapshot(
                raw_model_output,
                llm_catalog=bundle.llm_discovery_catalog,
            )
            metrics = {**metrics, **llm_diag}

        pkg = RawFlowDiscoveryExperimentPackage(
            app_id=app_id,
            run_id=rid,
            input_refs=dict(bundle.input_refs),
            compressed_catalog_package=bundle.compressed_catalog_package,
            llm_discovery_catalog=bundle.llm_discovery_catalog,
            prompt_snapshot=prompt_snap,
            model_config_snapshot=cfg_snap,
            raw_model_output=raw_model_output,
            repaired_model_output=repaired_output,
            validation_metrics=metrics,
            discovery_warnings=list(warnings),
            created_at=utc_now_iso(),
        )

        if write_to_path is not None:
            raw_output_writer.write_package(write_to_path, pkg)

        return pkg


__all__ = ["ExperimentRawFlowDiscoveryRunner", "default_model_caller"]
