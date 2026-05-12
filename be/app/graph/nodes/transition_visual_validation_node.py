"""
Transition Visual Validation Node — Agent 4.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph.state.graph_state import PipelineState
from app.services.transition_visual_validation_service import run_transition_visual_validation
from app.core.logging import log_event

async def transition_visual_validation_node(state: PipelineState, db: AsyncSession) -> Dict[str, Any]:
    """
    Executes visual validation for transitions discovered in the previous step.
    """
    run_id = state["run_id"]
    flow_discovery_result = state.get("flow_discovery_result")
    
    if not flow_discovery_result:
        return {
            "warnings": ["No flow discovery result found to validate transitions."],
            "current_node": "transition_visual_validation_node"
        }

    result = await run_transition_visual_validation(
        db=db,
        run_id=run_id,
        flow_discovery_result=flow_discovery_result,
        canonical_state_set=state.get("canonical_state_set"),
    )

    return {
        "validated_flow_package": result,
        "current_node": "transition_visual_validation_node",
        "completed_nodes": ["transition_visual_validation_node"]
    }
