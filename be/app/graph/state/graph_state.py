"""
PipelineState — shared TypedDict state for the entire LangGraph pipeline.
"""
from __future__ import annotations

import operator
from typing import Any, Dict, List, Optional, Annotated
from typing_extensions import TypedDict




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

    # ── Input Data ───────────
    raw_image_ids: List[str]                          # image IDs loaded from DB

    
    # ── 7-Agent Pipeline Packages (Strict JSON) ──
    
    # A1: UI State Extraction
    ui_state_package: Dict[str, Any]
    state_catalog: List[Dict[str, Any]]               # verbatim extracted states (A1 output)
    interaction_group_catalog: List[Dict[str, Any]]   # V2
    
    # A2 v2: Screen Behaviour Intent Extraction (NEW)
    screen_intent_package: Dict[str, Any]
    
    # A3: Flow Context Builder (NEW)
    flow_context_package: Dict[str, Any]
    
    # A4: Intent-aware Flow Discovery (previously A3)
    flow_discovery_result: Dict[str, Any]
    
    # A5: Behaviour Contract Builder (previously A5 Behaviour Intent Inference)
    behaviour_contract_package: Dict[str, Any]
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

    # Feedback Loop Control
    scenario_revision_round: int                      # 0 = first pass, 1 = retry (max)
    revision_suggestions: List[Dict[str, Any]]        # A7's revision suggestions for A6

