"""
Graph Runner — builds and executes the LangGraph pipeline.
"""
from __future__ import annotations

import functools
from langgraph.graph import END, START, StateGraph

from app.graph.nodes.global_flow_discovery_node import global_flow_discovery_node
from app.graph.nodes.generate_tests_node import generate_tests_node
from app.graph.nodes.graph_finalizer_node import graph_finalizer_node
from app.graph.nodes.init_run_context_node import init_run_context_node
from app.graph.nodes.joint_screen_understanding_node import joint_screen_understanding_node
from app.graph.nodes.output_assembly_node import output_assembly_node
from app.graph.nodes.scenario_evidence_audit_node import scenario_evidence_audit_node
from app.graph.nodes.representation_compression_node import representation_compression_node
from app.graph.state.graph_state import PipelineState


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


def _route_after_init(state: PipelineState) -> str:
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "joint_screen_understanding_node"


_route_after_screen_understanding = _make_route("representation_compression_node")
_route_after_compression = _make_route("global_flow_discovery_node")
_route_after_global_flow = _make_route("generate_tests_node")
_route_after_generate_tests = _make_route("scenario_evidence_audit_node")


def _route_after_scenario_evidence_audit(state: PipelineState) -> str:
    """Audit no longer loops back into scenario generation — always assembly unless stopped."""
    if state.get("should_stop"):
        return "graph_finalizer_node"
    return "output_assembly_node"


# ──────────────────────────────────────────────
# Graph builder
# ──────────────────────────────────────────────


async def build_graph(db, run_id: str) -> StateGraph:
    """Compile the LangGraph StateGraph with injected DB session."""
    _ = run_id  # kept for API stability with callers
    graph = StateGraph(PipelineState)

    # Bind nodes with db
    init_node = functools.partial(init_run_context_node, db=db)
    joint_node = functools.partial(joint_screen_understanding_node, db=db)
    compress_node = functools.partial(representation_compression_node, db=db)
    global_flow_node = functools.partial(global_flow_discovery_node, db=db)
    generate_tests = functools.partial(generate_tests_node, db=db)
    validation_node = functools.partial(scenario_evidence_audit_node, db=db)
    assembly_node = functools.partial(output_assembly_node, db=db)
    finalizer_node = functools.partial(graph_finalizer_node, db=db)

    graph.add_node("init_run_context_node", init_node)
    graph.add_node("joint_screen_understanding_node", joint_node)
    graph.add_node("representation_compression_node", compress_node)
    graph.add_node("global_flow_discovery_node", global_flow_node)
    graph.add_node("generate_tests_node", generate_tests)
    graph.add_node("scenario_evidence_audit_node", validation_node)
    graph.add_node("output_assembly_node", assembly_node)
    graph.add_node("graph_finalizer_node", finalizer_node)

    graph.add_edge(START, "init_run_context_node")

    graph.add_conditional_edges(
        "init_run_context_node",
        _route_after_init,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "joint_screen_understanding_node": "joint_screen_understanding_node",
        },
    )
    graph.add_conditional_edges(
        "joint_screen_understanding_node",
        _route_after_screen_understanding,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "representation_compression_node": "representation_compression_node",
        },
    )

    graph.add_conditional_edges(
        "representation_compression_node",
        _route_after_compression,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "global_flow_discovery_node": "global_flow_discovery_node",
        },
    )

    graph.add_conditional_edges(
        "global_flow_discovery_node",
        _route_after_global_flow,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "generate_tests_node": "generate_tests_node",
        },
    )

    graph.add_conditional_edges(
        "generate_tests_node",
        _route_after_generate_tests,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "scenario_evidence_audit_node": "scenario_evidence_audit_node",
        },
    )

    graph.add_conditional_edges(
        "scenario_evidence_audit_node",
        _route_after_scenario_evidence_audit,
        {
            "graph_finalizer_node": "graph_finalizer_node",
            "output_assembly_node": "output_assembly_node",
        },
    )

    graph.add_edge("output_assembly_node", "graph_finalizer_node")

    graph.add_edge("graph_finalizer_node", END)

    return graph
