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

    
    # ── Pipeline packages (graph node order, strict JSON payloads) ──
    
    # UI state evidence extraction (vision V2)
    ui_state_package: Dict[str, Any]
    state_catalog: List[Dict[str, Any]]
    interaction_group_catalog: List[Dict[str, Any]]
    
    # Screen behaviour intent extraction V2
    screen_intent_package: Dict[str, Any]
    
    # Flow context builder (deterministic merge of states + intents)
    flow_context_package: Dict[str, Any]
    
    # Intent-aware flow discovery
    flow_discovery_result: Dict[str, Any]
    
    # Behaviour contract builder (structured behaviour intents + persistence)
    intent_package: Dict[str, Any]
    
    # BDD scenario generation
    scenario_draft_package: Dict[str, Any]
    
    # Scenario evidence audit (structured validation report)
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

    # Scenario evidence audit (Agent 7) — suggestions are report/UI only (no automatic regeneration).
    audit_revision_suggestions: List[Dict[str, Any]]

