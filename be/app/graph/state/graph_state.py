"""
PipelineState — shared TypedDict state for the entire LangGraph pipeline.

Only a subset of fields is used per phase. Later phases will add more fields
(e.g. duplicate_groups, ui_extractions, flow_graph, scenarios) without
breaking earlier nodes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class ImagePreprocessingResult(TypedDict):
    image_id: str
    original_filename: str
    is_valid: bool
    quality_status: str
    invalid_reason: Optional[str]
    normalized_uri: Optional[str]
    thumbnail_uri: Optional[str]
    warnings: List[str]
    preprocessing_json: Dict[str, Any]


class PipelineState(TypedDict, total=False):
    """
    Shared state flowing through the LangGraph pipeline.

    Populated incrementally — each node reads its inputs and writes its outputs.
    Fields not yet populated by earlier nodes will be absent or None.
    """

    # ── Identity ─────────────────────────────
    run_id: str
    job_id: Optional[str]

    # ── Run config (read from DB at start) ───
    config: Dict[str, Any]

    # ── Phase 2: Image Preprocessing ─────────
    raw_image_ids: List[str]                          # image IDs loaded from DB
    valid_images: List[ImagePreprocessingResult]      # passed all checks
    invalid_images: List[ImagePreprocessingResult]    # failed at least one check
    image_quality_report: Dict[str, Any]              # full report dict
    preprocessing_warnings: List[str]                 # cross-image warnings

    # ── Phase 3: Duplicate Detection ─────────
    duplicate_groups: List[Dict[str, Any]]
    canonical_images: List[str]                        # IDs of images to process in Phase 4+
    duplicate_detection_report: Dict[str, Any]

    # ── Pipeline control ─────────────────────
    errors: List[str]                                 # accumulated non-fatal errors
    should_stop: bool                                 # set True to halt pipeline early
    stop_reason: Optional[str]                        # e.g. "NO_VALID_IMAGES"
    node_name: Optional[str]                          # current node (for logging)
