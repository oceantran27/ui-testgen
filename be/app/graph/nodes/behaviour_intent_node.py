"""
LangGraph node for Behaviour Intent Inference (Agent 5).
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.behaviour_intent_service import run_behaviour_intent_inference
from app.services.graph_progress import persist_run_graph_progress

async def behaviour_intent_inference_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    run_id = state["run_id"]
    await persist_run_graph_progress(run_id, "behaviour_intent_inference_node")
    
    validated_flow_package = state.get("validated_flow_package")
    if not validated_flow_package:
        # Fallback
        validated_flow_package = {"validated_flows": state.get("flow_clusters", [])}

    result = await run_behaviour_intent_inference(
        db=db,
        run_id=run_id,
        validated_flow_package=validated_flow_package
    )

    return {
        "intent_package": result,
        "current_node": "behaviour_intent_inference_node",
        "completed_nodes": ["behaviour_intent_inference_node"]
    }
