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
from app.db.models.ui_state import UIState
from app.model_providers import model_adapter
from app.model_providers.base import ImageInput
from app.model_providers.schemas import UIStateExtractionV2Result
from app.services.storage_service import storage_service
from app.services.ui_state_evidence_persist import (
    generate_state_id_for_image,
    persist_ui_state_from_v2_result,
)


def _generate_artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


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
                exc_info=(type(response), response, response.__traceback__),
            )
            failed_extractions_count += 1
            failed_items.append(img.id)
            failed_state = UIState(
                id=generate_state_id_for_image(img),
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
                id=generate_state_id_for_image(img),
                run_id=run_id,
                image_id=img.id,
                page_type="unknown_page",
                extraction_status="failed",
                extraction_error=str(response.error),
            )
            db.add(failed_state)
            continue

        result_data: UIStateExtractionV2Result = response.parsed_output.model_copy(deep=True)

        state_row, counts = persist_ui_state_from_v2_result(db, run_id, img, result_data)
        extracted_states.append(state_row)
        extracted_states_count += 1
        canonical_screen_type = state_row["screen_type"]
        page_type_distribution[canonical_screen_type] = page_type_distribution.get(
            canonical_screen_type, 0
        ) + 1
        total_ui_elements += counts["total_ui_elements"]
        total_actionable_elements += counts["total_actionable_elements"]
        total_feedback_elements += counts["total_feedback_elements"]

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
        "interaction_group_catalog": [
            {**ig, "source_state_id": state["state_id"]}
            for state in extracted_states
            for ig in state.get("interaction_groups", [])
        ],
        "report": report,
    }


run_ui_state_extraction = run_ui_state_evidence_extraction
