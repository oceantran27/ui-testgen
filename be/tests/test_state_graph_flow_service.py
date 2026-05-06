"""Tests for state graph flow normalization."""

from app.schemas.state_graph import StateGraphFlowItem
from app.services.state_graph_flow_service import normalize_and_complete_flows


def test_normalize_filters_unknown_and_adds_orphan():
    known = {"a", "b", "c"}
    flows = [
        StateGraphFlowItem(id="f1", name="Main", nodes=["a", "ghost", "b"]),
        StateGraphFlowItem(id="f2", name="Other", nodes=["a"]),
    ]
    out = normalize_and_complete_flows(known, flows)
    ids = {f.id for f in out}
    # c must appear somewhere
    all_nodes = [n for f in out for n in f.nodes]
    assert "c" in all_nodes
    main = next(f for f in out if f.id == "f1")
    assert main.nodes == ["a", "b"]


def test_normalize_empty_flows_creates_singletons():
    known = {"x", "y"}
    out = normalize_and_complete_flows(known, [])
    assert len(out) == 2
    assert all(len(f.nodes) == 1 for f in out)
