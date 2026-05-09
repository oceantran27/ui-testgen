"""
Behaviour Intent Inference Node — LangGraph node for Phase 10.
"""
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import log_event, logger
from app.graph.state.graph_state import PipelineState
from app.services.behaviour_intent_service import BehaviourIntentService

NODE_NAME = "behaviour_intent_inference"

async def behaviour_intent_inference_node(
    state: PipelineState,
    db: AsyncSession,
) -> PipelineState:
    """
    Node for Phase 10 — Behaviour Intent Inference.
    Infors user intentions and goals using LLM.
    """
    run_id = state["run_id"]
    flow_ids = state.get("detected_flows", [])
    state_catalog = state.get("state_catalog", [])
    
    log_event(f"{NODE_NAME}_started", run_id=run_id, node_name=NODE_NAME)

    try:
        result = await BehaviourIntentService.run_inference(
            db=db, 
            run_id=run_id, 
            flow_ids=flow_ids,
            state_catalog=state_catalog
        )

        if "error" in result:
            logger.error(f"[{NODE_NAME}] Inference failed: {result['error']}")
            return {
                "current_node": NODE_NAME,
                "failed_nodes": [NODE_NAME],
                "errors": [result["error"]],
                "should_stop": True,
                "graph_status": "failed"
            }

        updates: Dict[str, Any] = {
            "current_node": NODE_NAME,
            "completed_nodes": [NODE_NAME],
            "behaviour_intents": result["behaviour_intents"],
            "behaviour_intent_report": result["report"],
        }

        # Check if we have any generatable intents
        has_generatable = any(intent.get("confidence", 0.0) >= 0.3 for intent in result["behaviour_intents"])
        if not has_generatable and result["behaviour_intents"]:
             # All intents are low confidence or failed
             logger.warning(f"[{NODE_NAME}] No high-confidence intents inferred.")

        return updates

    except Exception as e:
        logger.exception(f"[{NODE_NAME}] Unexpected error for run {run_id}: {e}")
        return {
            "current_node": NODE_NAME,
            "failed_nodes": [NODE_NAME],
            "errors": [str(e)],
            "should_stop": True,
            "graph_status": "failed"
        }
