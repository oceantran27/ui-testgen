"""
Envelope for persisted raw-flow-discovery experiment artefacts (Sprint 2 writer).

Production mapping:

- ``compressed_catalog_package``: e.g. from ``run_build_compressed_catalog`` or fixtures
- ``llm_discovery_catalog``: ``build_llm_discovery_catalog(compressed_catalog_package)``
- ``raw_model_output``: structured LLM payload before repair (matches ``GlobalFlowDiscoveryResult`` shape)
- ``repaired_model_output``: after ``validate_and_repair_global_flow_discovery``
- ``validation_metrics``: merged pre-scan plus repair metrics (see adapters ``build_validation_snapshot``)
- ``discovery_warnings``: ``repaired_model_output.discovery_warnings`` consolidated list

All dict fields intentionally stay loosely typed JSON for forward compatibility with the production schema.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from experiments.flow_discovery import config
from experiments.flow_discovery.io_utils import utc_now_iso


class RawFlowDiscoveryExperimentPackage(BaseModel):
    schema_version: str = Field(default=config.RAW_OUTPUT_SCHEMA_VERSION)

    app_id: str
    run_id: Optional[str] = None

    input_refs: Dict[str, Any] = Field(default_factory=dict)

    compressed_catalog_package: Dict[str, Any]
    llm_discovery_catalog: Dict[str, Any]

    prompt_snapshot: Dict[str, Any] = Field(default_factory=dict)
    model_config_snapshot: Dict[str, Any] = Field(default_factory=dict)

    raw_model_output: Dict[str, Any]
    repaired_model_output: Optional[Dict[str, Any]] = None

    validation_metrics: Dict[str, Any] = Field(default_factory=dict)
    discovery_warnings: List[str] = Field(default_factory=list)

    created_at: str = Field(default_factory=utc_now_iso)

    model_config = ConfigDict(extra="ignore", protected_namespaces=())

    @field_validator("schema_version")
    @classmethod
    def _schema_matches_package(cls, v: str) -> str:
        if v != config.RAW_OUTPUT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {config.RAW_OUTPUT_SCHEMA_VERSION!r}, got {v!r}",
            )
        return v

    @field_validator("app_id")
    @classmethod
    def _non_empty_app_id(cls, v: str) -> str:
        stripped = str(v).strip()
        if not stripped:
            raise ValueError("app_id must be non-empty")
        return stripped
