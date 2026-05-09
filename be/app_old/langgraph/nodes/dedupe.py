import os
import json
import logging
import asyncio

from app.services.image_dedup_service import dedupe_image_paths
from app.langgraph.state import PipelineGraphState

logger = logging.getLogger(__name__)

async def dedupe_node(state: PipelineGraphState):
    """
    Deduplicates images and updates the state.
    """
    input_id = state["input_id"]
    saved_paths = state["saved_paths"]
    out_dir = state["out_dir"]
    
    logger.info(f"[state-graph-pipeline] phase dedupe begin input_id={input_id} paths={len(saved_paths)}")
    
    # Run deduplication in thread
    dedup = await asyncio.to_thread(dedupe_image_paths, saved_paths)
    
    logger.info(f"[state-graph-pipeline] phase dedupe end input_id={input_id} canonical={len(dedup.canonical_paths)}")
    
    # Optional: write debug JSON
    try:
        with open(os.path.join(out_dir, "dedup.json"), "w", encoding="utf-8") as f:
            json.dump({
                "canonical_paths": dedup.canonical_paths,
                "canonical_image_ids": dedup.canonical_image_ids,
                "input_path_to_image_id": dedup.input_path_to_image_id,
                "dropped_paths": dedup.dropped_paths,
            }, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning(f"Could not write artifact dedup.json: {exc}")

    if not dedup.canonical_paths:
        raise ValueError("No images remain after deduplication")

    return {
        "canonical_paths": dedup.canonical_paths,
        "canonical_image_ids": dedup.canonical_image_ids,
        "input_path_to_image_id": dedup.input_path_to_image_id
    }
