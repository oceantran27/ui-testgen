from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ImageMetaInRawOutput(BaseModel):
    image_id: str = ""
    source_path: str = ""
    relative_path: str
    filename: str = ""
    stem: str = ""
    extension: str = ""
    image_uri_used_for_model: Optional[str] = None


class ModelCallMeta(BaseModel):
    prompt_name: str = ""
    prompt_version: str = "v1"
    provider: str = ""
    model_name: str = ""
    status: str
    error_message: Optional[str] = None
    created_at: str = ""
    latency_ms: Optional[int] = None
    retry_count: int = 0


class ExperimentRawOutputDocument(BaseModel):
    schema_version: str
    experiment_name: str = "ui_state_extraction"
    image: ImageMetaInRawOutput
    model_call: ModelCallMeta
    raw_model_output: Optional[dict[str, Any]] = None
