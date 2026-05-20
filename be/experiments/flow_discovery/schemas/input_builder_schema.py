"""Pydantic contracts for joint raw → compressed catalog input builder."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JointRawFileRecord(BaseModel):
    raw_file_path: str
    raw_file_name: str
    source_image_id: str
    original_filename: Optional[str] = None
    raw_payload: Dict[str, Any]


class NormalizedJointOutput(BaseModel):
    source_image_id: str
    raw_file_name: str
    ui_state: Dict[str, Any]
    screen_intents: Dict[str, Any]
    warnings: List[str] = Field(default_factory=list)


class InputBuilderResult(BaseModel):
    app_id: str
    experiment_run_id: str

    ui_state_package: Dict[str, Any]
    screen_intent_package: Dict[str, Any]
    compressed_catalog_package: Dict[str, Any]

    build_report: Dict[str, Any]


__all__ = [
    "InputBuilderResult",
    "JointRawFileRecord",
    "NormalizedJointOutput",
]
