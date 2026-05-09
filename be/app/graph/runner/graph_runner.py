"""
Graph Runner — builds and executes the LangGraph pipeline.

Current graph (Phase 2):
  START → image_preprocessing_node → (conditional) → END or future_phases

The conditional edge checks state["should_stop"]:
  - True  → END  (no valid images, or node error)
  - False → END  (Phase 3+ not yet wired; will be extended)
"""
from __future__ import annotations

import functools
from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.core.logging import logger, log_event
from app.db.session import AsyncSessionLocal
from app.graph.state.graph_state import PipelineState
from app.graph.nodes.image_preprocessing_node import image_preprocessing_node
from app.graph.nodes.duplicate_detection_node import duplicate_detection_node


# ──────────────────────────────────────────────
# Conditional edge functions
# ──────────────────────────────────────────────

def _route_after_preprocessing(state: PipelineState) -> Literal["end", "duplicate_detection"]:
    """
    Decide next node after image preprocessing.
    """
    if state.get("should_stop"):
        return "end"
    return "duplicate_detection"


def _route_after_duplicate_detection(state: PipelineState) -> Literal["end", "next"]:
    """
    Decide next node after duplicate detection.
    """
    if state.get("should_stop"):
        return "end"
    # Phase 4 (UI State Understanding) will be wired here
    return "end"


# ──────────────────────────────────────────────
# Graph builder (legacy/static builder - updated node names)
# ──────────────────────────────────────────────

def _build_graph() -> StateGraph:
    """Compile the LangGraph StateGraph."""
    graph = StateGraph(PipelineState)

    graph.add_node("image_preprocessing", _noop_placeholder)
    graph.add_node("duplicate_detection", _noop_placeholder)

    graph.add_edge(START, "image_preprocessing")
    graph.add_conditional_edges(
        "image_preprocessing",
        _route_after_preprocessing,
        {"end": END, "duplicate_detection": "duplicate_detection"},
    )
    graph.add_conditional_edges(
        "duplicate_detection",
        _route_after_duplicate_detection,
        {"end": END, "next": END},
    )

    return graph.compile()


def _noop_placeholder(state: PipelineState) -> PipelineState:
    """Placeholder node — replaced at runtime via partial injection."""
    return state


# ──────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────

async def run_pipeline(run_id: str, job_id: str | None = None) -> dict:
    """
    Execute the full LangGraph pipeline for a run.
    """
    log_event("pipeline_started", run_id=run_id, job_id=job_id)

    initial_state: PipelineState = {
        "run_id": run_id,
        "job_id": job_id,
        "config": {},
        "errors": [],
        "should_stop": False,
        "stop_reason": None,
        "node_name": None,
    }

    async with AsyncSessionLocal() as db:
        # Build graph with db injected via partial
        graph = StateGraph(PipelineState)

        preprocessing_with_db = functools.partial(image_preprocessing_node, db=db)
        duplicate_with_db = functools.partial(duplicate_detection_node, db=db)

        graph.add_node("image_preprocessing", preprocessing_with_db)
        graph.add_node("duplicate_detection", duplicate_with_db)

        graph.add_edge(START, "image_preprocessing")
        graph.add_conditional_edges(
            "image_preprocessing",
            _route_after_preprocessing,
            {"end": END, "duplicate_detection": "duplicate_detection"},
        )
        graph.add_conditional_edges(
            "duplicate_detection",
            _route_after_duplicate_detection,
            {"end": END, "next": END},
        )
        compiled = graph.compile()

        try:
            final_state = await compiled.ainvoke(initial_state)
            log_event("pipeline_completed", run_id=run_id, job_id=job_id)
            return final_state
        except Exception as e:
            logger.exception(f"Pipeline error for run {run_id}: {e}")
            log_event("pipeline_error", run_id=run_id, job_id=job_id, error_code=str(e))
            raise
