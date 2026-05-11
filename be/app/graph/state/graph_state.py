"""
PipelineState — shared TypedDict state for the entire LangGraph pipeline.

Only a subset of fields is used per phase. Later phases will add more fields
(e.g. duplicate_groups, ui_extractions, flow_graph, scenarios) without
breaking earlier nodes.
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
    invalid_images: List[ImagePreprocessingResult]    # failed at least one check
    image_quality_report: Dict[str, Any]              # full report dict
    preprocessing_warnings: Annotated[List[str], operator.add]

    # ── Phase 3: Duplicate Detection (Exact & Semantic) ──
    exact_duplicate_groups: List[Dict[str, Any]]
    exact_canonical_images: List[str]
    exact_duplicate_report: Dict[str, Any]
    
    semantic_duplicate_groups: List[Dict[str, Any]]
    canonical_state_catalog: List[Dict[str, Any]]
    semantic_duplicate_report: Dict[str, Any]
    
    # ── Phase 6: UI State Understanding ──
    state_catalog: List[Dict[str, Any]]               # list of extracted UI states
    ui_state_extraction_report: Dict[str, Any]

    # ── Phase 8: Flow Discovery (LLM-guided) ──
    flow_clusters: List[Dict[str, Any]]
    unassigned_state_ids: List[str]
    flow_discovery_report: Dict[str, Any]
    detected_flows: List[str]                         # list of flow IDs

    # ── Phase 10: Behaviour Intent Inference ──
    behaviour_intents: List[Dict[str, Any]]
    behaviour_intent_report: Dict[str, Any]

    # ── Phase 11: Behaviour Scenario Generation ──
    draft_scenarios: List[Dict[str, Any]]
    scenario_generation_report: Dict[str, Any]

    # ── Phase 12: Scenario Grounding & Validation ──
    validated_scenarios: List[Dict[str, Any]]
    low_confidence_scenarios: List[Dict[str, Any]]
    needs_revision_scenarios: List[Dict[str, Any]]
    rejected_scenarios: List[Dict[str, Any]]
    scenario_validation_report: Dict[str, Any]

    # ── Phase 14: Output Assembly ──
    final_output: Dict[str, Any]
    final_artifacts: List[Dict[str, Any]]

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

    # ── Phase 5: Model Provider Tracking ─────
    model_calls_summary: Annotated[List[Dict[str, Any]], operator.add]   # one entry per model call
    model_total_tokens: int                           # accumulated across all calls
    model_total_latency_ms: int                       # accumulated across all calls
    model_warnings: Annotated[List[str], operator.add]
    model_errors: Annotated[List[str], operator.add]
