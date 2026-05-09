"""
Graph Runner — builds and executes the LangGraph pipeline.

Phase 4 Graph:
  START
  → init_run_context_node
  → image_preprocessing_node
  → (conditional: route_after_preprocessing)
  → duplicate_detection_node
  → (conditional: route_after_duplicate_detection)
  → graph_finalizer_node
  → END
"""
from __future__ import annotations

import functools
from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.core.logging import logger, log_event
from app.db.session import AsyncSessionLocal
from app.graph.state.graph_state import PipelineState
from app.graph.nodes.init_run_context_node import init_run_context_node
from app.graph.nodes.image_preprocessing_node import image_preprocessing_node
from app.graph.nodes.duplicate_detection_node import duplicate_detection_node
from app.graph.nodes.graph_finalizer_node import graph_finalizer_node
from app.graph.nodes.ui_state_node import ui_state_extraction_node
from app.graph.nodes.input_level_node import input_level_detection_node
from app.graph.nodes.flow_discovery_node import flow_discovery_node
from app.graph.nodes.missing_step_node import missing_step_analysis_node
from app.graph.nodes.behaviour_intent_node import behaviour_intent_inference_node
from app.graph.nodes.scenario_generation_node import behaviour_scenario_generation_node
from app.graph.nodes.scenario_validation_node import scenario_validation_node
from app.graph.nodes.scenario_curation_node import scenario_curation_node


# ──────────────────────────────────────────────
# Conditional edge functions
# ──────────────────────────────────────────────

def _route_after_preprocessing(state: PipelineState) -> Literal["graph_finalizer_node", "duplicate_detection_node"]:
    """
    Decide next node after image preprocessing.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "duplicate_detection_node"


def _route_after_duplicate_detection(state: PipelineState) -> Literal["graph_finalizer_node", "ui_state_extraction_node"]:
    """
    Decide next node after duplicate detection.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "ui_state_extraction_node"

def _route_after_ui_state_extraction(state: PipelineState) -> Literal["graph_finalizer_node", "input_level_detection_node"]:
    """
    Decide next node after UI state extraction.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "input_level_detection_node"


def _route_after_input_level_detection(state: PipelineState) -> Literal["graph_finalizer_node", "flow_discovery_node"]:
    """
    Decide next node after input level detection.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "flow_discovery_node"


def _route_after_flow_discovery(state: PipelineState) -> Literal["graph_finalizer_node", "missing_step_analysis_node"]:
    """
    Decide next node after flow discovery.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "missing_step_analysis_node"


def _route_after_missing_step_analysis(state: PipelineState) -> Literal["graph_finalizer_node", "behaviour_intent_inference_node"]:
    """
    Decide next node after missing step analysis.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "behaviour_intent_inference_node"


def _route_after_behaviour_intent_inference(state: PipelineState) -> Literal["graph_finalizer_node", "behaviour_scenario_generation_node"]:
    """
    Decide next node after behaviour intent inference.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "behaviour_scenario_generation_node"


def _route_after_behaviour_scenario_generation(state: PipelineState) -> Literal["graph_finalizer_node", "scenario_validation_node"]:
    """
    Decide next node after behaviour scenario generation.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "scenario_validation_node"


def _route_after_scenario_validation(state: PipelineState) -> Literal["graph_finalizer_node", "scenario_curation_node"]:
    """
    Decide next node after scenario validation.
    """
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "scenario_curation_node"


def _route_after_scenario_curation(state: PipelineState) -> Literal["graph_finalizer_node"]:
    """
    Decide next node after scenario curation.
    """
    # Phase 13 currently ends here.
    return "graph_finalizer_node"


# ──────────────────────────────────────────────
# Graph builder
# ──────────────────────────────────────────────

def build_graph(db) -> StateGraph:
    """Compile the LangGraph StateGraph with injected DB session."""
    graph = StateGraph(PipelineState)

    # Bind nodes with db
    init_node = functools.partial(init_run_context_node, db=db)
    preprocessing_node = functools.partial(image_preprocessing_node, db=db)
    duplicate_node = functools.partial(duplicate_detection_node, db=db)
    ui_state_node = functools.partial(ui_state_extraction_node, db=db)
    input_level_node = functools.partial(input_level_detection_node, db=db)
    flow_node = functools.partial(flow_discovery_node, db=db)
    missing_step_node = functools.partial(missing_step_analysis_node, db=db)
    intent_node = functools.partial(behaviour_intent_inference_node, db=db)
    generation_node = functools.partial(behaviour_scenario_generation_node, db=db)
    validation_node = functools.partial(scenario_validation_node, db=db)
    curation_node = functools.partial(scenario_curation_node, db=db)
    finalizer_node = functools.partial(graph_finalizer_node, db=db)

    # Add nodes
    graph.add_node("init_run_context_node", init_node)
    graph.add_node("image_preprocessing_node", preprocessing_node)
    graph.add_node("duplicate_detection_node", duplicate_node)
    graph.add_node("ui_state_extraction_node", ui_state_node)
    graph.add_node("input_level_detection_node", input_level_node)
    graph.add_node("flow_discovery_node", flow_node)
    graph.add_node("missing_step_analysis_node", missing_step_node)
    graph.add_node("behaviour_intent_inference_node", intent_node)
    graph.add_node("behaviour_scenario_generation_node", generation_node)
    graph.add_node("scenario_validation_node", validation_node)
    graph.add_node("scenario_curation_node", curation_node)
    graph.add_node("graph_finalizer_node", finalizer_node)

    # Add edges
    graph.add_edge(START, "init_run_context_node")
    graph.add_edge("init_run_context_node", "image_preprocessing_node")
    
    graph.add_conditional_edges(
        "image_preprocessing_node",
        _route_after_preprocessing,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "duplicate_detection_node": "duplicate_detection_node"
        },
    )
    
    graph.add_conditional_edges(
        "duplicate_detection_node",
        _route_after_duplicate_detection,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "ui_state_extraction_node": "ui_state_extraction_node"
        },
    )

    graph.add_conditional_edges(
        "ui_state_extraction_node",
        _route_after_ui_state_extraction,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "input_level_detection_node": "input_level_detection_node"
        },
    )

    graph.add_conditional_edges(
        "input_level_detection_node",
        _route_after_input_level_detection,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "flow_discovery_node": "flow_discovery_node"
        },
    )

    graph.add_conditional_edges(
        "flow_discovery_node",
        _route_after_flow_discovery,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "missing_step_analysis_node": "missing_step_analysis_node"
        },
    )

    graph.add_conditional_edges(
        "missing_step_analysis_node",
        _route_after_missing_step_analysis,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "behaviour_intent_inference_node": "behaviour_intent_inference_node"
        },
    )

    graph.add_conditional_edges(
        "behaviour_intent_inference_node",
        _route_after_behaviour_intent_inference,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "behaviour_scenario_generation_node": "behaviour_scenario_generation_node"
        },
    )

    graph.add_conditional_edges(
        "behaviour_scenario_generation_node",
        _route_after_behaviour_scenario_generation,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "scenario_validation_node": "scenario_validation_node"
        },
    )

    graph.add_conditional_edges(
        "scenario_validation_node",
        _route_after_scenario_validation,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "scenario_curation_node": "scenario_curation_node"
        },
    )

    graph.add_conditional_edges(
        "scenario_curation_node",
        _route_after_scenario_curation,
        {
            "graph_finalizer_node": "graph_finalizer_node"
        },
    )

    graph.add_edge("graph_finalizer_node", END)

    return graph
