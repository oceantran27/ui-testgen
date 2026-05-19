"""Manifest written by module 2 after converting raw outputs to temp ground truth."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class TempGroundTruthManifestItem(BaseModel):
    image_id: str
    relative_path: str
    raw_output_path: str
    temp_ground_truth_path: str
    conversion_status: str
    review_priority: str = "low"
    auto_flag_count: int = 0
    invalid_reference_count: int = 0
    error_message: str | None = None


class TempGroundTruthManifest(BaseModel):
    schema_version: str
    source_raw_manifest: str = ""
    source_mode: str = "manifest"
    total_raw_outputs: int = 0
    total_converted: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    total_high_priority_review: int = 0
    total_medium_priority_review: int = 0
    total_low_priority_review: int = 0
    items: List[TempGroundTruthManifestItem] = Field(default_factory=list)
