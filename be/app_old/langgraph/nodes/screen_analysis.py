import os
import json
import logging
import asyncio
from typing import Any

from app.schemas.state_graph import StateGraphInputScreen
from app.services.state_graph_screen_metadata import build_state_graph_screen_dict
from app.services.ui_extraction_payload import filter_scoped_ui_extraction, user_intent_input_to_minified_json
from app.services.ui_extraction_service import extract_ui_extraction_gemini_sync
from app.services.user_intent_service import generate_user_intents_openai_sync

logger = logging.getLogger(__name__)

# State schema for the map step
from typing import TypedDict

class ScreenAnalysisInput(TypedDict):
    path: str
    image_id: str
    extract_model: str
    intent_model: str
    out_dir: str

async def process_screen_node(state: ScreenAnalysisInput):
    """
    Process a single screen: UI Extraction -> User Intent Generation.
    This node is designed to be executed in parallel using LangGraph's Send API.
    """
    path = state["path"]
    image_id = state["image_id"]
    extract_model = state["extract_model"]
    intent_model = state["intent_model"]
    out_dir = state["out_dir"]
    
    logger.info(f"Processing screen image_id={image_id}")
    
    def _sync_extract_and_intent():
        # 1. UI Extraction
        ui_ext, _h_sec = extract_ui_extraction_gemini_sync(path, extract_model)
        
        # 2. Scope & Minify
        scoped = filter_scoped_ui_extraction(ui_ext)
        minified = user_intent_input_to_minified_json(scoped)
        
        # 3. User Intent
        intents = generate_user_intents_openai_sync(image_id, minified, intent_model)
        return ui_ext, intents

    ui_extraction, intents = await asyncio.to_thread(_sync_extract_and_intent)
    
    user_intents_list = intents.model_dump(mode="json")["user_intents"]
    ui_dump = ui_extraction.model_dump(mode="json", exclude_none=True)
    
    screen_doc = StateGraphInputScreen.model_validate(
        build_state_graph_screen_dict(
            image_id=image_id,
            extraction=ui_extraction,
            user_intents=user_intents_list,
        )
    ).model_dump(mode="json")
    
    try:
        with open(os.path.join(out_dir, f"screen_{image_id[:16]}.json"), "w", encoding="utf-8") as f:
            json.dump({
                "image_id": image_id,
                "ui_extraction": ui_dump,
                "user_intents": user_intents_list,
                "interactive_element_count": len(ui_extraction.controls),
                "state_graph_screen": screen_doc,
            }, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning(f"Could not write artifact screen_{image_id[:16]}.json: {exc}")

    # Return partial updates to PipelineGraphState
    return {
        "ui_extractions": {image_id: ui_dump},
        "user_intents_by_image": {image_id: user_intents_list},
        "screen_docs": {image_id: screen_doc}
    }
