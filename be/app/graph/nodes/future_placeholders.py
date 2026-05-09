"""
Future Placeholders Nodes — Stub nodes for AI phases (5+).
"""
from app.core.logging import log_event
from app.graph.state.graph_state import PipelineState

async def ui_state_extraction_node(state: PipelineState) -> PipelineState:
    log_event("graph_node_skipped", run_id=state["run_id"], node_name="ui_state_extraction_node", reason="NOT_IMPLEMENTED")
    return {"current_node": "ui_state_extraction_node", "warnings": ["ui_state_extraction_node is NOT_IMPLEMENTED"]}

async def flow_discovery_node(state: PipelineState) -> PipelineState:
    log_event("graph_node_skipped", run_id=state["run_id"], node_name="flow_discovery_node", reason="NOT_IMPLEMENTED")
    return {"current_node": "flow_discovery_node", "warnings": ["flow_discovery_node is NOT_IMPLEMENTED"]}
