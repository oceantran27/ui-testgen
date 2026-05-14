"""
PipelineState — shared TypedDict state for the entire LangGraph pipeline.
"""
from __future__ import annotations

import operator
from typing import Any, Dict, List, Optional, Annotated
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


# Custom reducer for dicts: updates existing dict instead of overwriting
def merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    merged = a.copy() if a else {}
    if b:
        merged.update(b)
    return merged


class PipelineState(TypedDict, total=False):
    """
    Shared state flowing through the LangGraph pipeline.
    """

    # ── Identity ─────────────────────────────
    run_id: str
    job_id: Optional[str]

    # ── Run config (merge reducer) ───────────
    config: Annotated[Dict[str, Any], merge_dicts]

    # ── Phase 2: Image Preprocessing ─────────
    raw_image_ids: List[str]                          # image IDs loaded from DB
    valid_images: List[ImagePreprocessingResult]      # passed all checks
    image_quality_report: Dict[str, Any]              # full report dict
    preprocessing_warnings: Annotated[List[str], operator.add]

    # ── Phase 3: Exact Duplicate Detection ──
    exact_duplicate_groups: List[Dict[str, Any]]
    exact_canonical_images: List[str]
    exact_duplicate_report: Dict[str, Any]
    
    # ── 7-Agent Pipeline Packages (Strict JSON) ──
    
    # A1: UI State Extraction
    ui_state_package: Dict[str, Any]
    state_catalog: List[Dict[str, Any]]               # verbatim extracted states (A1 output)
    
    # A2: Semantic Canonicalization
    canonical_state_set: Dict[str, Any]
    
    # A3: UI Flow Discovery
    flow_discovery_result: Dict[str, Any]
    
    # A5: Behaviour Intent Inference
    intent_package: Dict[str, Any]
    
    # A6: BDD Scenario Generation
    scenario_draft_package: Dict[str, Any]
    
    # A7: Scenario Validation
    validated_scenario_package: Dict[str, Any]

    # Final assembled artifact (output_assembly_node) — must be declared or LangGraph drops it.
    final_output: Dict[str, Any]

    # ── Phase 4: Pipeline control & Metrics ──
    warnings: Annotated[List[str], operator.add]      # accumulated warnings
    errors: Annotated[List[str], operator.add]        # accumulated non-fatal errors
    artifacts: Annotated[List[Dict[str, Any]], operator.add] # log of artifacts created
    metrics: Annotated[Dict[str, Any], merge_dicts]   # key-value metrics from nodes
    
    current_node: str                                 # currently executing node
    completed_nodes: Annotated[List[str], operator.add]
    failed_nodes: Annotated[List[str], operator.add]
    graph_status: str                                 # running, partial_completed, failed, completed
    started_at: str                                   # ISO format timestamp
    completed_at: Optional[str]                       # ISO format timestamp
    
    should_stop: bool                                 # set True to halt pipeline early
    stop_reason: Optional[str]                        # e.g. "NO_VALID_IMAGES"
