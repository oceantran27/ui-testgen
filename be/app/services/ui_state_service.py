"""
UI State Service — Phase 6 implementation.
Extracts UI elements and state information from canonical images using VLM.
"""
import uuid
from typing import Any, Dict, List
import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.image import Image
from app.db.models.ui_state import UIState
from app.db.models.ui_element import UIElement
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service
from app.model_providers import model_adapter
from app.model_providers.schemas import UIStateExtractionResult, UIElementData
from app.model_providers.base import ImageInput
import json

def _generate_state_id() -> str:
    return f"st_{uuid.uuid4().hex[:12]}"

def _generate_element_id() -> str:
    return f"el_{uuid.uuid4().hex[:12]}"

def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


def _convert_bbox(gemini_bbox: List[int]) -> Dict[str, float]:
    """
    Convert Gemini bbox [ymin, xmin, ymax, xmax] (0-1000 scale)
    to internal format {x_min, y_min, x_max, y_max} (0.0 - 1.0).
    """
    if len(gemini_bbox) != 4:
        return {"x_min": 0.0, "y_min": 0.0, "x_max": 0.0, "y_max": 0.0}
    
    ymin, xmin, ymax, xmax = gemini_bbox
    return {
        "x_min": max(0.0, min(1.0, xmin / 1000.0)),
        "y_min": max(0.0, min(1.0, ymin / 1000.0)),
        "x_max": max(0.0, min(1.0, xmax / 1000.0)),
        "y_max": max(0.0, min(1.0, ymax / 1000.0)),
    }


def _generate_state_signature(page_type: str, elements: List[UIElementData]) -> str:
    """Generate a compact semantic signature for the state."""
    inputs = []
    actions = []
    feedback = "none"
    
    for el in elements:
        if el.type in ["input", "textarea", "checkbox", "radio", "dropdown"]:
            if el.label or el.placeholder or el.text:
                inputs.append((el.label or el.placeholder or el.text)[:20])
        elif el.actionable and el.action_type in ["click", "submit", "navigate"]:
            if el.label or el.text:
                actions.append((el.label or el.text)[:20])
        elif el.is_feedback and el.feedback_type in ["error", "success", "warning"]:
            feedback = el.feedback_type

    inputs_str = ",".join(inputs[:5]) if inputs else "none"
    actions_str = ",".join(actions[:5]) if actions else "none"
    
    return f"{page_type}|inputs:{inputs_str}|actions:{actions_str}|feedback:{feedback}"


async def run_ui_state_extraction(db: AsyncSession, run_id: str, canonical_images: List[str]) -> Dict[str, Any]:
    """
    Execute Phase 6 for a given list of canonical image IDs.
    Returns the state catalog and report.
    """
    start_time = time.time()
    log_event("ui_state_extraction_started", run_id=run_id, node_name="ui_state_extraction")

    if not canonical_images:
        log_event("ui_state_extraction_skipped", run_id=run_id, reason="NO_CANONICAL_IMAGES")
        return {"state_catalog": [], "report": {}}

    # Load canonical images from DB
    result = await db.execute(
        select(Image).where(Image.id.in_(canonical_images), Image.run_id == run_id)
    )
    images = list(result.scalars().all())

    state_catalog = []
    extracted_states_count = 0
    failed_extractions_count = 0
    
    page_type_distribution: Dict[str, int] = {}
    total_ui_elements = 0
    total_actionable_elements = 0
    total_feedback_elements = 0
    failed_items = []
    warnings = []

    for idx, img in enumerate(images):
        if not img.normalized_uri:
            warnings.append(f"Image {img.id} missing normalized_uri. Skipped.")
            failed_extractions_count += 1
            failed_items.append(img.id)
            continue
            
        system_instruction = (
            "You are an expert UI Analyst. Your task is to extract structural and semantic information "
            "from the provided UI screenshot. Return a structured JSON matching the requested schema.\n"
            "Rules:\n"
            "- Only describe elements that are VISIBLE in the screenshot.\n"
            "- Do NOT hallucinate elements that might exist but are not currently visible.\n"
            "- Use the provided Enums strictly.\n"
            "- Extract text accurately. If text is illegible, leave it empty or mark low confidence.\n"
            "- Actionable elements are things the user can interact with (buttons, inputs, links).\n"
            "- Feedback elements are system messages (errors, success toasts, validation text).\n"
            "- Bounding boxes must be returned as [ymin, xmin, ymax, xmax] scaled 0-1000.\n"
        )
        
        user_instruction = (
            "Analyze this screenshot and extract the UI state. Identify the page type, visible texts, "
            "and all significant UI elements. Determine if they are actionable or feedback elements."
        )
        
        image_input = ImageInput(image_id=img.id, storage_uri=img.normalized_uri)
        
        response = await model_adapter.call_vision_structured(
            task_name="ui_state_extraction",
            run_id=run_id,
            node_name="ui_state_extraction_node",
            system_instruction=system_instruction,
            user_instruction=user_instruction,
            image_inputs=[image_input],
            output_schema=UIStateExtractionResult,
            prompt_name="ui_state_extraction_prompt",
            prompt_version="v1",
        )
        
        if response.status.value != "success" or not response.parsed_output:
            logger.error(f"UI Extraction failed for image {img.id}: {response.error}")
            failed_extractions_count += 1
            failed_items.append(img.id)
            
            # Save failed state
            failed_state = UIState(
                id=_generate_state_id(),
                run_id=run_id,
                image_id=img.id,
                page_type="unknown_page",
                extraction_status="failed",
                extraction_error=str(response.error)
            )
            db.add(failed_state)
            continue

        result_data: UIStateExtractionResult = response.parsed_output
        state_id = _generate_state_id()
        
        # Calculate derived confidence
        conf_label = "low"
        if result_data.confidence >= 0.85:
            conf_label = "high"
        elif result_data.confidence >= 0.65:
            conf_label = "medium"
            
        signature = _generate_state_signature(result_data.page_type, result_data.ui_elements)
        
        # Save UIState
        db_state = UIState(
            id=state_id,
            run_id=run_id,
            image_id=img.id,
            page_type=result_data.page_type,
            state_summary=result_data.state_summary,
            state_signature=signature,
            confidence=result_data.confidence,
            confidence_label=conf_label,
            has_form=result_data.has_form,
            has_table=result_data.has_table,
            has_modal=result_data.has_modal,
            has_feedback=result_data.has_feedback,
            extraction_status="success",
        )
        db.add(db_state)
        
        extracted_states_count += 1
        page_type_distribution[result_data.page_type] = page_type_distribution.get(result_data.page_type, 0) + 1
        
        actionable_count = 0
        feedback_count = 0
        
        # Save UIElements
        for idx, el_data in enumerate(result_data.ui_elements):
            bbox = _convert_bbox(el_data.bbox_ymin_xmin_ymax_xmax)
            
            db_el = UIElement(
                id=f"{state_id}_E{idx+1}",
                state_id=state_id,
                run_id=run_id,
                image_id=img.id,
                type=el_data.type,
                label=el_data.label,
                text=el_data.text,
                placeholder=el_data.placeholder,
                bbox_xmin=bbox["x_min"],
                bbox_ymin=bbox["y_min"],
                bbox_xmax=bbox["x_max"],
                bbox_ymax=bbox["y_max"],
                actionable=el_data.actionable,
                action_type=el_data.action_type,
                is_feedback=el_data.is_feedback,
                feedback_type=el_data.feedback_type,
                confidence=el_data.confidence,
            )
            db.add(db_el)
            
            total_ui_elements += 1
            if el_data.actionable:
                actionable_count += 1
                total_actionable_elements += 1
            if el_data.is_feedback:
                feedback_count += 1
                total_feedback_elements += 1
                
        if result_data.warnings:
            warnings.extend([f"[{img.id}] {w}" for w in result_data.warnings])

        # Add to catalog
        state_catalog.append({
            "state_id": state_id,
            "image_id": img.id,
            "page_type": result_data.page_type,
            "state_summary": result_data.state_summary,
            "state_signature": signature,
            "visible_texts": result_data.visible_texts,
            "ui_elements": [el.model_dump() for el in result_data.ui_elements],
            "actionable_elements": [el.model_dump() for el in result_data.ui_elements if el.actionable],
            "feedback_elements": [el.model_dump() for el in result_data.ui_elements if el.is_feedback],
            "has_form": result_data.has_form,
            "has_table": result_data.has_table,
            "has_modal": result_data.has_modal,
            "has_feedback": result_data.has_feedback,
            "element_count": len(result_data.ui_elements),
            "actionable_element_count": actionable_count,
            "feedback_element_count": feedback_count,
            "confidence": result_data.confidence,
        })
        
    await db.commit()
    
    # 7. Build Report
    report = {
        "run_id": run_id,
        "canonical_images_count": len(images),
        "extracted_states_count": extracted_states_count,
        "failed_extractions_count": failed_extractions_count,
        "state_ids": [s["state_id"] for s in state_catalog],
        "page_type_distribution": page_type_distribution,
        "total_ui_elements": total_ui_elements,
        "total_actionable_elements": total_actionable_elements,
        "total_feedback_elements": total_feedback_elements,
        "failed_items": failed_items,
        "warnings": warnings
    }
    
    if settings.SAVE_UI_STATE_EXTRACTION_REPORT:
        report_bytes = json.dumps(report, indent=2).encode("utf-8")
        report_key = f"artifacts/{run_id}/ui_state_extraction/ui_state_extraction_report.json"
        report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")

        artifact = Artifact(
            id=_generate_artifact_id(),
            run_id=run_id,
            artifact_type="ui_state_extraction_report",
            node_name="ui_state_extraction",
            storage_uri=report_uri,
            metadata_json={"extracted_states_count": extracted_states_count},
        )
        db.add(artifact)
        await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("ui_state_extraction_completed", run_id=run_id, duration_ms=duration_ms)

    return {
        "state_catalog": state_catalog,
        "report": report
    }
