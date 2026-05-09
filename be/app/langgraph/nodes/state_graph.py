import os
import json
import logging
import asyncio

from app.langgraph.state import PipelineGraphState
from app.services.state_graph_flow_service import normalize_and_complete_flows, run_state_graph_flow_sync

logger = logging.getLogger(__name__)

async def state_graph_node(state: PipelineGraphState):
    """
    Infers state graph flows from the combined screen extractions and intents.
    """
    input_id = state["input_id"]
    flow_model = state["flow_model"]
    screen_docs = state["screen_docs"]
    canonical_image_ids = state["canonical_image_ids"]
    out_dir = state["out_dir"]
    
    known_ids = set(canonical_image_ids)
    
    logger.info(f"[state-graph-pipeline] phase state_graph begin input_id={input_id} flow_model={flow_model} screen_ids={len(known_ids)}")
    
    # We ordered screen_docs by canonical_image_ids to maintain stable order if needed,
    # but dicts don't guarantee order. Let's just create a list of screens
    screens = [screen_docs[iid] for iid in canonical_image_ids if iid in screen_docs]
    bundle = {"screens": screens}
    
    try:
        with open(os.path.join(out_dir, "screens_bundle.json"), "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning(f"Could not write artifact screens_bundle.json: {exc}")

    # Run state graph flow inference
    flows_raw = await asyncio.to_thread(
        run_state_graph_flow_sync,
        bundle,
        flow_model,
        fallback_image_ids=known_ids,
    )
    
    flows_final = normalize_and_complete_flows(known_ids, flows_raw)
    
    try:
        with open(os.path.join(out_dir, "flows_raw.json"), "w", encoding="utf-8") as f:
            json.dump([f.model_dump(mode="json") for f in flows_raw], f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning(f"Could not write artifact flows_raw.json: {exc}")

    logger.info(f"[state-graph-pipeline] phase state_graph end input_id={input_id} flows={len(flows_final)}")
    
    return {
        "flows": flows_final
    }
