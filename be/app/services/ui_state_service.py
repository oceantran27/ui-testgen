"""
UI State Service — extracts UI states from canonical images (Agent 1).

Builds a UIStatePackage (extracted_states) for semantic canonicalization per prompts.
"""
import asyncio
import json
import time
import uuid
from typing import Any, Dict, List

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
from app.model_providers.schemas import UIElementA1, UIStateExtractionResult
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


def _generate_state_signature(page_type: str, elements: List[UIElementA1]) -> str:
    inputs: List[str] = []
    actions: List[str] = []
    feedback = "none"
    for el in elements:
        if el.type in ("input", "textarea", "checkbox", "radio", "dropdown"):
            label = el.label or el.text or ""
            if label:
                inputs.append(label[:20])
        elif el.actionable:
            label = el.label or el.text or ""
            if label:
                actions.append(label[:20])
        if el.is_feedback and el.feedback_type:
            feedback = el.feedback_type
    return f"{page_type}|inputs:{','.join(inputs[:5]) or 'none'}|actions:{','.join(actions[:5]) or 'none'}|feedback:{feedback}"


def _flags_from_elements(elements: List[UIElementA1]) -> tuple[bool, bool, bool, bool]:
    has_form = any(
        el.type in ("input", "textarea", "dropdown", "checkbox", "radio", "form")
        for el in elements
    )
    has_table = any(el.type == "table" for el in elements)
    has_modal = any(el.type in ("modal", "drawer", "toast", "banner", "alert") for el in elements)
    has_feedback = any(el.is_feedback for el in elements)
    return has_form, has_table, has_modal, has_feedback


def _safe_element_db_id(state_id: str, element_id: str, idx: int) -> str:
    raw = f"{state_id}_{element_id}"
    if len(raw) > 200:
        return f"{state_id}_E{idx}"
    return raw


async def run_ui_state_extraction(
    db: AsyncSession, run_id: str, canonical_images: List[str]
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("ui_state_extraction_started", run_id=run_id, node_name="ui_state_extraction")

    if not canonical_images:
        log_event("ui_state_extraction_skipped", run_id=run_id, reason="NO_CANONICAL_IMAGES")
        return {
            "ui_state_package_id": f"ui_pkg_{uuid.uuid4().hex[:12]}",
            "extracted_states": [],
            "state_catalog": [],
            "report": {},
        }

    result = await db.execute(
        select(Image).where(Image.id.in_(canonical_images), Image.run_id == run_id)
    )
    by_id = {row.id: row for row in result.scalars().all()}
    ordered_images = [by_id[cid] for cid in canonical_images if cid in by_id]

    images_for_vision = [img for img in ordered_images if img.normalized_uri]
    system_instruction = prompt_manager.get_prompt("ui_state_extraction")

    semaphore = asyncio.Semaphore(settings.UI_STATE_EXTRACTION_MAX_CONCURRENCY)

    async def _vision_one(img: Image):
        async with semaphore:
            user_instruction = (
                "Analyze this screenshot and extract the UI state per your contract "
                "(state_id may use image id; use source_image_id exactly as provided in JSON metadata)."
            )
            user_instruction += f'\nMetadata JSON: {{"image_id": "{img.id}", "image_uri": "{img.normalized_uri}"}}'
            image_input = ImageInput(image_id=img.id, storage_uri=img.normalized_uri)
            return await model_adapter.call_vision_structured(
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
        if not img.normalized_uri:
            warnings.append(f"Image {img.id} missing normalized_uri. Skipped.")
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

        result_data: UIStateExtractionResult = response.parsed_output
        state_id = _generate_state_id()
        conf = _confidence_from_extraction(result_data.extraction_status, result_data.state_quality)
        conf_label = _confidence_label(conf)
        has_form, has_table, has_modal, has_feedback = _flags_from_elements(result_data.ui_elements)
        signature = _generate_state_signature(result_data.page_type, result_data.ui_elements)

        db_state = UIState(
            id=state_id,
            run_id=run_id,
            image_id=img.id,
            page_type=result_data.page_type,
            state_summary=result_data.state_summary,
            state_signature=signature,
            confidence=conf,
            confidence_label=conf_label,
            has_form=has_form,
            has_table=has_table,
            has_modal=has_modal,
            has_feedback=has_feedback,
            state_quality=result_data.state_quality.model_dump(),
            extraction_status=result_data.extraction_status,
        )
        db.add(db_state)

        actionable_count = 0
        feedback_count = 0

        for idx, el_data in enumerate(result_data.ui_elements):
            bbox = _convert_bbox(el_data.bbox)
            db_el = UIElement(
                id=_safe_element_db_id(state_id, el_data.element_id, idx),
                state_id=state_id,
                run_id=run_id,
                image_id=img.id,
                type=el_data.type,
                label=el_data.label,
                text=el_data.text,
                placeholder=None,
                bbox_xmin=bbox["x_min"],
                bbox_ymin=bbox["y_min"],
                bbox_xmax=bbox["x_max"],
                bbox_ymax=bbox["y_max"],
                actionable=el_data.actionable,
                action_type=None,
                semantic_role=el_data.semantic_role,
                visibility=el_data.visibility,
                visible=True,
                is_feedback=el_data.is_feedback,
                feedback_type=None,
                confidence=0.0,
            )
            db.add(db_el)
            total_ui_elements += 1
            if el_data.actionable:
                actionable_count += 1
                total_actionable_elements += 1
            if el_data.is_feedback:
                feedback_count += 1
                total_feedback_elements += 1

        state_row = {
            "extraction_status": result_data.extraction_status,
            "state_id": state_id,
            "source_image_id": img.id,
            "page_type": result_data.page_type,
            "state_summary": result_data.state_summary,
            "visible_texts": [v.model_dump() for v in result_data.visible_texts],
            "ui_elements": [u.model_dump() for u in result_data.ui_elements],
            "feedback_elements": [f.model_dump() for f in result_data.feedback_elements],
            "primary_action_candidates": [p.model_dump() for p in result_data.primary_action_candidates],
            "state_quality": result_data.state_quality.model_dump(),
        }
        extracted_states.append(state_row)
        extracted_states_count += 1
        page_type_distribution[result_data.page_type] = page_type_distribution.get(result_data.page_type, 0) + 1
        for w in result_data.state_quality.warnings:
            warnings.append(f"[{img.id}] {w}")

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
        "report": report,
    }
