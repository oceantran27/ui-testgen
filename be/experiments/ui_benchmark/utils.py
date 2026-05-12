import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _be_root() -> Path:
    return Path(__file__).resolve().parents[2]

def ensure_sys_path() -> None:
    root = str(_be_root())
    if root not in sys.path:
        sys.path.insert(0, root)

ensure_sys_path()

import asyncio
from app.core.config import settings
from app.core.prompt_manager import prompt_manager
from app.model_providers import model_adapter
from app.model_providers.base import ImageInput
from app.model_providers.schemas import UIStateExtractionResult, UIElementA1

def load_images_from_dir(directory: Path) -> List[Path]:
    """Loads and sorts images from a directory (01.png, 02.png, ...)."""
    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    files = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in allowed]
    # Simple sort by name works well for 01.png, 02.png format
    return sorted(files, key=lambda x: x.name)

async def call_ui_extraction(
    image_path: Path, 
    run_id: str, 
    model_name: Optional[str] = None, 
    provider: Optional[str] = None
) -> Tuple[UIStateExtractionResult, int]:
    """Calls the VLM to extract UI state from a local image directly, bypassing storage/preprocess."""
    
    # 1. Read bytes directly from local file
    raw_bytes = image_path.read_bytes()
    suffix = image_path.suffix.lower().lstrip(".")
    mime_type = f"image/{suffix}"
    if suffix in ("jpg", "jpeg"):
        mime_type = "image/jpeg"
    
    # 2. Call VLM with direct bytes
    system_instruction = prompt_manager.get_prompt("ui_state_extraction")
    user_instruction = "Analyze this screenshot and extract the UI state per your contract."
    
    image_input = ImageInput(
        image_id=image_path.stem,
        image_bytes=raw_bytes,
        mime_type=mime_type
    )

    response = await model_adapter.call_vision_structured(
        task_name="ui_state_extraction",
        run_id=run_id,
        node_name="benchmark_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        image_inputs=[image_input],
        output_schema=UIStateExtractionResult,
        model_name_override=model_name or "",
        provider_override=provider or "",
    )
    
    if response.status.value != "success" or not response.parsed_output:
        raise RuntimeError(f"Extraction failed for {image_path.name}: {response.error}")
        
    return response.parsed_output, response.latency_ms

def trim_ui_elements(result: UIStateExtractionResult) -> List[Dict[str, Any]]:
    """Prunes UI elements to keep only the requested fields + bbox for matching."""
    trimmed = []
    # UIStateExtractionResult has extracted_states which contains UIStateA1
    # Actually, let's look at the schema again. 
    # UIStateExtractionResult -> extracted_states: List[UIStateA1]
    # UIStateA1 -> ui_elements: List[UIElementA1]
    
    for state in result.extracted_states:
        for el in state.ui_elements:
            trimmed.append({
                "type": el.type,
                "label": el.label,
                "text": el.text,
                "actionable": el.actionable,
                "is_feedback": el.is_feedback,
                "bbox": el.bbox # [ymin, xmin, ymax, xmax]
            })
    return trimmed

def calculate_iou(bbox1: List[float], bbox2: List[float]) -> float:
    """Calculates Intersection over Union (IoU) for two bboxes [ymin, xmin, ymax, xmax]."""
    y_min1, x_min1, y_max1, x_max1 = bbox1
    y_min2, x_min2, y_max2, x_max2 = bbox2

    # Intersection
    inter_ymin = max(y_min1, y_min2)
    inter_xmin = max(x_min1, x_min2)
    inter_ymax = min(y_max1, y_max2)
    inter_xmax = min(x_max1, x_max2)

    if inter_ymax <= inter_ymin or inter_xmax <= inter_xmin:
        return 0.0

    inter_area = (inter_ymax - inter_ymin) * (inter_xmax - inter_xmin)

    # Union
    area1 = (y_max1 - y_min1) * (x_max1 - x_min1)
    area2 = (y_max2 - y_min2) * (x_max2 - x_min2)
    union_area = area1 + area2 - inter_area

    return inter_area / union_area if union_area > 0 else 0.0

def match_elements(gt_el: Dict[str, Any], model_el: Dict[str, Any]) -> bool:
    """
    Implements the dual matching logic:
    1. If text/label is present: match by attributes + text/label.
    2. If text/label is null: match by attributes + bbox IoU >= 0.5.
    """
    # Core attributes must match
    if (gt_el["type"] != model_el["type"] or 
        gt_el["actionable"] != model_el["actionable"] or 
        gt_el["is_feedback"] != model_el["is_feedback"]):
        return False

    gt_text = (gt_el.get("text") or "").strip()
    gt_label = (gt_el.get("label") or "").strip()
    model_text = (model_el.get("text") or "").strip()
    model_label = (model_el.get("label") or "").strip()

    has_gt_text = bool(gt_text or gt_label)
    
    if has_gt_text:
        # Match by text or label (case insensitive)
        text_match = (gt_text.lower() == model_text.lower()) if gt_text else False
        label_match = (gt_label.lower() == model_label.lower()) if gt_label else False
        return text_match or label_match
    else:
        # Match by BBox overlap
        iou = calculate_iou(gt_el["bbox"], model_el["bbox"])
        return iou >= 0.5
