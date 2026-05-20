from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class ModelConfigSnapshot(BaseModel):
    """Joint screen understanding settings as configured when module 1 ran."""

    configured_provider: str = ""
    configured_model_name: str = ""
    prompt_name: str = ""
    prompt_version: str = "v1"
    max_concurrency: int = 1


class ModelLatencySummary(BaseModel):
    """Aggregate latency for one actual (provider, model_name) seen during the run."""

    provider: str
    model_name: str
    call_count: int
    avg_latency_ms: float
    min_latency_ms: int
    max_latency_ms: int


class ManifestItem(BaseModel):
    image_id: str
    relative_path: str
    raw_output_path: str
    status: str
    skip_reason: str | None = None
    latency_ms: int | None = None
    provider: str | None = None
    model_name: str | None = None


class RawOutputManifest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    schema_version: str
    run_id: str = ""
    image_root_url_or_path: str
    total_images_discovered: int
    total_images_enqueued: int = 0
    max_images_to_process: int = 0
    total_success: int
    total_failed: int
    total_skipped: int = 0
    experiment_model_settings: ModelConfigSnapshot | None = None
    model_latency_summary: List[ModelLatencySummary] = Field(default_factory=list)
    timing_notes: List[str] = Field(default_factory=list)
    items: List[ManifestItem] = Field(default_factory=list)
