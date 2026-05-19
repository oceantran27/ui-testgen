from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class ManifestItem(BaseModel):
    image_id: str
    relative_path: str
    raw_output_path: str
    status: str
    skip_reason: str | None = None


class RawOutputManifest(BaseModel):
    schema_version: str
    image_root_url_or_path: str
    total_images_discovered: int
    total_images_enqueued: int = 0
    max_images_to_process: int = 0
    total_success: int
    total_failed: int
    total_skipped: int = 0
    items: List[ManifestItem] = Field(default_factory=list)
