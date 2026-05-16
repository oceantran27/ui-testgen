"""
Graph Runner — builds and executes the LangGraph pipeline.
"""
from __future__ import annotations

import functools
from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.graph.state.graph_state import PipelineState
from app.graph.nodes.init_run_context_node import init_run_context_node
from app.graph.nodes.ui_state_evidence_extraction_node import ui_state_evidence_extraction_node
from app.graph.nodes.screen_intent_extraction_v2_node import screen_intent_extraction_v2_node
from app.graph.nodes.flow_context_builder_node import flow_context_builder_node
from app.graph.nodes.intent_aware_flow_discovery_node import intent_aware_flow_discovery_node
from app.graph.nodes.behaviour_contract_builder_node import behaviour_contract_builder_node
from app.graph.nodes.scenario_generation_node import behaviour_scenario_generation_node
from app.graph.nodes.scenario_evidence_audit_node import scenario_evidence_audit_node
from app.graph.nodes.output_assembly_node import output_assembly_node
from app.graph.nodes.graph_finalizer_node import graph_finalizer_node


# ──────────────────────────────────────────────
# Conditional edge functions
# ──────────────────────────────────────────────

def _make_route(next_node: str):
    """Factory to create routing functions that handle early stopping."""
    def _route(state: PipelineState) -> str:
        if state.get("should_stop"):
            return "graph_finalizer_node"
        return next_node
    return _route

_route_after_init = _make_route("ui_state_evidence_extraction_node")
_route_after_ui_state_extraction = _make_route("screen_intent_extraction_v2_node")
_route_after_screen_intent = _make_route("flow_context_builder_node")
_route_after_flow_context = _make_route("intent_aware_flow_discovery_node")
_route_after_flow_discovery = _make_route("behaviour_contract_builder_node")
_route_after_behaviour_contract = _make_route("behaviour_scenario_generation_node")
_route_after_behaviour_scenario_generation = _make_route("scenario_evidence_audit_node")
def _route_after_scenario_evidence_audit(state: PipelineState) -> str:
    if state.get("should_stop"):
        return "graph_finalizer_node"
    
    revision_round = state.get("scenario_revision_round", 0)
    revision_suggestions = state.get("revision_suggestions", [])
    
    # Retry if: round 0 (first pass) AND has revision suggestions
    if revision_round == 0 and revision_suggestions:
        return "behaviour_scenario_generation_node"
        
    return "output_assembly_node"


def _route_after_output_assembly(state: PipelineState) -> str:
    return "graph_finalizer_node"


# ──────────────────────────────────────────────
# Graph builder
# ──────────────────────────────────────────────

def build_graph(db) -> StateGraph:
    """Compile the LangGraph StateGraph with injected DB session."""
    graph = StateGraph(PipelineState)

    # Bind nodes with db
    init_node = functools.partial(init_run_context_node, db=db)
    ui_state_node = functools.partial(ui_state_evidence_extraction_node, db=db)
    screen_intent_node = functools.partial(screen_intent_extraction_v2_node, db=db)
    flow_context_node = functools.partial(flow_context_builder_node, db=db)
    llm_flow_node = functools.partial(intent_aware_flow_discovery_node, db=db)
    intent_node = functools.partial(behaviour_contract_builder_node, db=db)
    generation_node = functools.partial(behaviour_scenario_generation_node, db=db)
    validation_node = functools.partial(scenario_evidence_audit_node, db=db)
    assembly_node = functools.partial(output_assembly_node, db=db)
    finalizer_node = functools.partial(graph_finalizer_node, db=db)

    graph.add_node("init_run_context_node", init_node)
    graph.add_node("ui_state_evidence_extraction_node", ui_state_node)
    graph.add_node("screen_intent_extraction_v2_node", screen_intent_node)
    graph.add_node("flow_context_builder_node", flow_context_node)
    graph.add_node("intent_aware_flow_discovery_node", llm_flow_node)
    graph.add_node("behaviour_contract_builder_node", intent_node)
    graph.add_node("behaviour_scenario_generation_node", generation_node)
    graph.add_node("scenario_evidence_audit_node", validation_node)
    graph.add_node("output_assembly_node", assembly_node)
    graph.add_node("graph_finalizer_node", finalizer_node)

    # Add edges
    graph.add_edge(START, "init_run_context_node")
    graph.add_conditional_edges(
        "init_run_context_node",
        _route_after_init,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "ui_state_evidence_extraction_node": "ui_state_evidence_extraction_node",
        },
    )
    

    graph.add_conditional_edges(
        "ui_state_evidence_extraction_node",
        _route_after_ui_state_extraction,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "screen_intent_extraction_v2_node": "screen_intent_extraction_v2_node"
        },
    )

    graph.add_conditional_edges(
        "screen_intent_extraction_v2_node",
        _route_after_screen_intent,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "flow_context_builder_node": "flow_context_builder_node"
        },
    )

    graph.add_conditional_edges(
        "flow_context_builder_node",
        _route_after_flow_context,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "intent_aware_flow_discovery_node": "intent_aware_flow_discovery_node"
        },
    )

    graph.add_conditional_edges(
        "intent_aware_flow_discovery_node",
        _route_after_flow_discovery,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "behaviour_contract_builder_node": "behaviour_contract_builder_node"
        },
    )

    graph.add_conditional_edges(
        "behaviour_contract_builder_node",
        _route_after_behaviour_contract,
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
            "scenario_evidence_audit_node": "scenario_evidence_audit_node"
        },
    )

    graph.add_conditional_edges(
        "scenario_evidence_audit_node",
        _route_after_scenario_evidence_audit,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "behaviour_scenario_generation_node": "behaviour_scenario_generation_node",
            "output_assembly_node": "output_assembly_node"
        },
    )


    graph.add_conditional_edges(
        "output_assembly_node",
        _route_after_output_assembly,
        {
            "graph_finalizer_node": "graph_finalizer_node"
        },
    )

    graph.add_edge("graph_finalizer_node", END)

    return graph
