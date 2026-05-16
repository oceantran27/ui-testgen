"""
UI State Service — extracts UI states from canonical images (Agent 1).

Builds a UIStatePackage (extracted_states) for semantic canonicalization per prompts.
"""
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.artifact import Artifact
from app.db.models.image import Image
from app.db.models.ui_element import UIElement
from app.db.models.ui_state import UIState
from app.model_providers import model_adapter
from app.model_providers.base import ImageInput
from app.model_providers.schemas import UIElementA1V2, UIActionA1V2, UIFeedbackA1V2, UIStateExtractionV2Result, InteractionGroupA1V2
from app.services.storage_service import storage_service


def _generate_state_id() -> str:
    return f"st_{uuid.uuid4().hex[:12]}"


def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


def _convert_bbox(normalized_0_1000: List[int]) -> Dict[str, float]:
    if len(normalized_0_1000) != 4:
        return {"x_min": 0.0, "y_min": 0.0, "x_max": 0.0, "y_max": 0.0}
    ymin, xmin, ymax, xmax = normalized_0_1000
    return {
        "x_min": max(0.0, min(1.0, xmin / 1000.0)),
        "y_min": max(0.0, min(1.0, ymin / 1000.0)),
        "x_max": max(0.0, min(1.0, xmax / 1000.0)),
        "y_max": max(0.0, min(1.0, ymax / 1000.0)),
    }


def _confidence_from_extraction(extraction_status: str, quality: Any) -> float:
    base = {"success": 0.88, "partial": 0.62, "failed": 0.05}.get(extraction_status, 0.5)
    if quality is None:
        return round(base, 3)
    vr = getattr(quality, "visual_readability", "") or ""
    ec = getattr(quality, "extraction_completeness", "") or ""
    if vr == "high" and ec == "complete":
        base = min(1.0, base + 0.08)
    elif vr == "low" or ec == "poor":
        base = max(0.05, base - 0.25)
    return round(base, 3)


def _confidence_label(conf: float) -> str:
    if conf >= 0.75:
        return "high"
    if conf >= 0.5:
        return "medium"
    return "low"


def _generate_state_signature(page_type: str, elements: List[UIElementA1V2], actions: List[UIActionA1V2], feedback_list: List[UIFeedbackA1V2]) -> str:
    inputs: List[str] = []
    action_labels: List[str] = []
    fb_type = "none"
    
    for el in elements:
        if el.element_type in ("input", "textarea", "checkbox", "radio", "select", "dropdown"):
            t = " ".join(el.text) if el.text else ""
            if t:
                inputs.append(t[:20])
    
    for act in actions:
        t = " ".join(act.text) if act.text else ""
        if t:
            action_labels.append(t[:20])
            
    if feedback_list:
        fb_type = feedback_list[0].feedback_type
        
    return f"{page_type}|inputs:{','.join(inputs[:5]) or 'none'}|actions:{','.join(action_labels[:5]) or 'none'}|feedback:{fb_type}"


def _flags_from_elements(elements: List[UIElementA1V2], actions: List[UIActionA1V2], feedback_list: List[UIFeedbackA1V2]) -> tuple[bool, bool, bool, bool]:
    has_form = any(
        el.element_type in ("input", "textarea", "select", "checkbox", "radio")
        for el in elements
    ) or any(act.action_type == "submit" for act in actions)
    
    has_table = any(el.element_type == "table" for el in elements)
    has_modal = any(el.element_type == "modal" for el in elements)
    has_feedback = len(feedback_list) > 0
    return has_form, has_table, has_modal, has_feedback


def _safe_element_db_id(state_id: str, element_id: str, idx: int) -> str:
    raw = f"{state_id}_{element_id}"
    if len(raw) > 200:
        return f"{state_id}_E{idx}"
    return raw


async def run_ui_state_evidence_extraction(
    db: AsyncSession, run_id: str, image_ids: List[str]
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("ui_state_extraction_started", run_id=run_id, node_name="ui_state_extraction")

    if not image_ids:
        log_event("ui_state_extraction_skipped", run_id=run_id, reason="NO_IMAGE_IDS")
        return {
            "ui_state_package_id": f"ui_pkg_{uuid.uuid4().hex[:12]}",
            "extracted_states": [],
            "state_catalog": [],
            "report": {},
        }

    result = await db.execute(
        select(Image).where(Image.id.in_(image_ids), Image.run_id == run_id)
    )
    by_id = {img.id: img for img in result.scalars().all()}
    ordered_images = [by_id[cid] for cid in image_ids if cid in by_id]

    images_for_vision = [img for img in ordered_images if img.storage_uri]
    system_instruction = prompt_manager.get_prompt("prompt_ui_state_evidence_extraction_v2")

    semaphore = asyncio.Semaphore(settings.UI_STATE_EXTRACTION_MAX_CONCURRENCY)

    async def _vision_one(img: Image):
        async with semaphore:
            user_instruction = (
                "Analyze this screenshot and extract the UI state per your contract "
                "(state_id may use image id; use source_image_id exactly as provided in JSON metadata)."
            )
            user_instruction += f'\nMetadata JSON: {{"image_id": "{img.id}", "image_uri": "{img.storage_uri}"}}'
            image_input = ImageInput(image_id=img.id, storage_uri=img.storage_uri)
            return await model_adapter.call_vision_structured(
                task_name="ui_state_extraction",
                run_id=run_id,
                node_name="ui_state_extraction_node",
                system_instruction=system_instruction,
                user_instruction=user_instruction,
                image_inputs=[image_input],
                output_schema=UIStateExtractionV2Result,
                prompt_name="prompt_ui_state_evidence_extraction_v2",
                prompt_version="v1",
                provider_override=settings.UI_STATE_EXTRACTION_PROVIDER,
                model_name_override=settings.UI_STATE_EXTRACTION_MODEL_NAME,
            )

    vision_outcomes = await asyncio.gather(
        *(_vision_one(img) for img in images_for_vision),
        return_exceptions=True,
    )
    vision_iter = iter(vision_outcomes)

    extracted_states: List[Dict[str, Any]] = []
    extracted_states_count = 0
    failed_extractions_count = 0
    page_type_distribution: Dict[str, int] = {}
    total_ui_elements = 0
    total_actionable_elements = 0
    total_feedback_elements = 0
    failed_items: List[str] = []
    warnings: List[str] = []

    ui_pkg_id = f"ui_pkg_{uuid.uuid4().hex[:12]}"

    for img in ordered_images:
        if not img.storage_uri:
            warnings.append(f"Image {img.id} missing storage_uri. Skipped.")
            failed_extractions_count += 1
            failed_items.append(img.id)
            continue

        response = next(vision_iter)
        if isinstance(response, Exception):
            logger.error(
                "UI Extraction failed for image %s: %s",
                img.id,
                response,
                exc_info=response,
            )
            failed_extractions_count += 1
            failed_items.append(img.id)
            failed_state = UIState(
                id=_generate_state_id(),
                run_id=run_id,
                image_id=img.id,
                page_type="unknown_page",
                extraction_status="failed",
                extraction_error=str(response),
            )
            db.add(failed_state)
            continue

        if response.status.value != "success" or not response.parsed_output:
            logger.error(f"UI Extraction failed for image {img.id}: {response.error}")
            failed_extractions_count += 1
            failed_items.append(img.id)
            failed_state = UIState(
                id=_generate_state_id(),
                run_id=run_id,
                image_id=img.id,
                page_type="unknown_page",
                extraction_status="failed",
                extraction_error=str(response.error),
            )
            db.add(failed_state)
            continue

        result_data: UIStateExtractionV2Result = response.parsed_output
        
        extraction_status = "success" if (result_data.visible_elements or result_data.available_actions) else "partial"
        state_quality_payload: Dict[str, Any] = {}
        # result_data no longer has extraction_warnings, but we can check if it's empty
        if not result_data.screen_purpose or result_data.screen_purpose == "null":
            extraction_status = "failed"

        state_id = _generate_state_id()
        conf = _confidence_from_extraction(extraction_status, None)
        conf_label = _confidence_label(conf)
        
        has_form, has_table, has_modal, has_feedback = _flags_from_elements(
            result_data.visible_elements, 
            result_data.available_actions, 
            result_data.visible_feedback
        )
        
        signature = _generate_state_signature(
            result_data.screen_type, 
            result_data.visible_elements,
            result_data.available_actions,
            result_data.visible_feedback
        )

        db_state = UIState(
            id=state_id,
            run_id=run_id,
            image_id=img.id,
            page_type=result_data.screen_type,
            screen_type=result_data.screen_type,
            screen_purpose=result_data.screen_purpose,
            domain=result_data.domain,
            state_summary=result_data.screen_purpose,
            state_signature=signature,
            confidence=conf,
            confidence_label=conf_label,
            has_form=has_form,
            has_table=has_table,
            has_modal=has_modal,
            has_feedback=has_feedback,
            state_quality=state_quality_payload,
            extraction_status=extraction_status,
        )
        db.add(db_state)

        # Interaction Groups Fallback
        if not result_data.interaction_groups and (result_data.visible_elements or result_data.available_actions or result_data.visible_feedback):
            fallback_group = InteractionGroupA1V2(
                group_id="ig_fallback",
                group_type="screen",
                group_label=f"Screen {result_data.screen_purpose}",
                element_ids=[el.element_id for el in result_data.visible_elements],
                action_ids=[ac.action_id for ac in result_data.available_actions],
                feedback_ids=[fb.feedback_id for fb in result_data.visible_feedback],
                primary_action_id=result_data.available_actions[0].action_id if result_data.available_actions else None,
                group_evidence=["auto-generated fallback group"],
                group_confidence="low"
            )
            result_data.interaction_groups = [fallback_group]

        # Prepend state_id to all interaction group reference IDs to make them globally unique
        for ig in result_data.interaction_groups:
            ig.group_id = f"{state_id}_{ig.group_id}"
            ig.element_ids = [f"{state_id}_{eid}" for eid in ig.element_ids]
            ig.action_ids = [f"{state_id}_{aid}" for aid in ig.action_ids]
            ig.feedback_ids = [f"{state_id}_{fid}" for fid in ig.feedback_ids]
            if ig.primary_action_id:
                ig.primary_action_id = f"{state_id}_{ig.primary_action_id}"

        db_state.interaction_groups_json = [ig.model_dump() for ig in result_data.interaction_groups]

        total_elements_in_state = 0
        
        # 1. Visible Elements
        for idx, el_data in enumerate(result_data.visible_elements):
            db_el = UIElement(
                id=f"{state_id}_{el_data.element_id}",
                state_id=state_id,
                run_id=run_id,
                image_id=img.id,
                type=el_data.element_type,
                text=el_data.text,
                actionable=False,
                is_feedback=False,
                visibility="fully_visible",
                visible=True,
                confidence=0.0,
            )
            db.add(db_el)
            total_elements_in_state += 1
            total_ui_elements += 1

        # 2. Available Actions
        for idx, act_data in enumerate(result_data.available_actions):
            db_el = UIElement(
                id=f"{state_id}_{act_data.action_id}",
                state_id=state_id,
                run_id=run_id,
                image_id=img.id,
                type="action",
                action_type=act_data.action_type,
                text=act_data.text,
                actionable=True,
                is_feedback=False,
                visibility="fully_visible",
                visible=True,
                confidence=0.0,
            )
            db.add(db_el)
            total_elements_in_state += 1
            total_ui_elements += 1
            total_actionable_elements += 1

        # 3. Visible Feedback
        for idx, fb_data in enumerate(result_data.visible_feedback):
            db_el = UIElement(
                id=f"{state_id}_{fb_data.feedback_id}",
                state_id=state_id,
                run_id=run_id,
                image_id=img.id,
                type="feedback",
                feedback_type=fb_data.feedback_type,
                text=fb_data.text,
                actionable=False,
                is_feedback=True,
                visibility="fully_visible",
                visible=True,
                confidence=0.0,
            )
            db.add(db_el)
            total_elements_in_state += 1
            total_ui_elements += 1
            total_feedback_elements += 1

        state_row = {
            "extraction_status": extraction_status,
            "state_id": state_id,
            "source_image_id": img.id,
            "page_type": result_data.screen_type,
            "screen_type": result_data.screen_type,
            "screen_purpose": result_data.screen_purpose,
            "domain": result_data.domain,
            "state_summary": result_data.screen_purpose,
            "visible_texts": [],
            "visible_elements": [e.model_dump() for e in result_data.visible_elements],
            "available_actions": [a.model_dump() for a in result_data.available_actions],
            "visible_feedback": [f.model_dump() for f in result_data.visible_feedback],
            "interaction_groups": [ig.model_dump() for ig in result_data.interaction_groups],
            "state_quality": state_quality_payload,
        }
        extracted_states.append(state_row)
        extracted_states_count += 1
        page_type_distribution[result_data.screen_type] = page_type_distribution.get(result_data.screen_type, 0) + 1

    await db.commit()

    report = {
        "run_id": run_id,
        "ui_state_package_id": ui_pkg_id,
        "canonical_images_count": len(ordered_images),
        "extracted_states_count": extracted_states_count,
        "failed_extractions_count": failed_extractions_count,
        "state_ids": [s["state_id"] for s in extracted_states],
        "page_type_distribution": page_type_distribution,
        "total_ui_elements": total_ui_elements,
        "total_actionable_elements": total_actionable_elements,
        "total_feedback_elements": total_feedback_elements,
        "failed_items": failed_items,
        "warnings": warnings,
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
        "schema_version": "1.0",
        "agent_name": "ui_state_extraction_agent",
        "ui_state_package_id": ui_pkg_id,
        "extracted_states": extracted_states,
        "state_catalog": extracted_states,
        "interaction_group_catalog": [ig for state in extracted_states for ig in state.get("interaction_groups", [])],
        "report": report,
    }

run_ui_state_extraction = run_ui_state_evidence_extraction
