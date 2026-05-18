"""Joint vision extraction: UI evidence + local screen intents in one structured call per image."""

from __future__ import annotations

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
from app.model_providers.schemas import JointScreenUnderstandingResult
from app.services.joint_screen_understanding_ids import prefix_screen_intent_payload
from app.services.joint_screen_understanding_validation import validate_joint_screen_understanding_structured
from app.services.screen_intent_prompt_render import render_phase2_taxonomy_system_suffix
from app.services.screen_intent_service import generate_screen_intent_id, persist_screen_intent_catalog_rows
from app.services.screen_intent_validation import process_screen_intents_for_state
from app.services.storage_service import storage_service
from app.services.ui_state_evidence_persist import generate_state_id_for_image, persist_ui_state_from_v2_result


def _artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


async def run_joint_screen_understanding(
    db: AsyncSession, run_id: str, image_ids: List[str]
) -> Dict[str, Any]:
    start_time = time.time()
    log_event("joint_screen_understanding_started", run_id=run_id, node_name="joint_screen_understanding")

    empty_pkg = {
        "ui_state_package": {
            "schema_version": "1.0",
            "agent_name": "joint_screen_understanding_agent",
            "extraction_mode": "joint",
            "ui_state_package_id": f"ui_pkg_{uuid.uuid4().hex[:12]}",
            "extracted_states": [],
            "state_catalog": [],
            "interaction_group_catalog": [],
            "report": {},
        },
        "state_catalog": [],
        "interaction_group_catalog": [],
        "screen_intent_package": {
            "schema_version": "2.1",
            "agent_name": "joint_screen_understanding_agent",
            "extraction_mode": "joint",
            "screen_intent_package_id": f"sbi_pkg_{uuid.uuid4().hex[:12]}",
            "screen_intent_catalog": [],
            "unresolved_screen_groups": [],
            "skipped_states": [],
            "intent_validation_summary": {},
            "report": {},
        },
        "report": {},
        "metrics": {"joint_screen_understanding_metrics": {}},
    }

    if not image_ids:
        log_event("joint_screen_understanding_skipped", run_id=run_id, reason="NO_IMAGE_IDS")
        return empty_pkg

    result = await db.execute(
        select(Image).where(Image.id.in_(image_ids), Image.run_id == run_id)
    )
    by_id = {img.id: img for img in result.scalars().all()}
    ordered_images = [by_id[cid] for cid in image_ids if cid in by_id]

    images_for_vision = [img for img in ordered_images if img.storage_uri]
    base_prompt = prompt_manager.get_prompt("prompt_joint_screen_understanding_v1").strip()
    system_instruction = f"{base_prompt}\n\n{render_phase2_taxonomy_system_suffix()}"

    semaphore = asyncio.Semaphore(settings.JOINT_SCREEN_UNDERSTANDING_MAX_CONCURRENCY)

    async def _vision_one(img: Image):
        async with semaphore:
            user_instruction = (
                "Analyze this screenshot. Return JSON matching JointScreenUnderstandingResult: "
                'top-level keys "ui_state" and "screen_intents". '
                "Use metadata image_id exactly.\n"
            )
            user_instruction += f'\nMetadata JSON: {{"image_id": "{img.id}", "image_uri": "{img.storage_uri}"}}'
            image_input = ImageInput(image_id=img.id, storage_uri=img.storage_uri)
            return await model_adapter.call_vision_structured(
                task_name="joint_screen_understanding",
                run_id=run_id,
                node_name="joint_screen_understanding_node",
                system_instruction=system_instruction,
                user_instruction=user_instruction,
                image_inputs=[image_input],
                output_schema=JointScreenUnderstandingResult,
                prompt_name="prompt_joint_screen_understanding_v1",
                prompt_version="v1",
                provider_override=settings.JOINT_SCREEN_UNDERSTANDING_PROVIDER,
                model_name_override=settings.JOINT_SCREEN_UNDERSTANDING_MODEL_NAME,
            )

    vision_outcomes = await asyncio.gather(
        *(_vision_one(img) for img in images_for_vision),
        return_exceptions=True,
    )
    vision_iter = iter(vision_outcomes)

    extracted_states: List[Dict[str, Any]] = []
    screen_intent_catalog: List[Dict[str, Any]] = []
    merged_unresolved: List[Dict[str, Any]] = []
    per_state_summaries: List[Dict[str, Any]] = []
    warnings: List[str] = []

    page_type_distribution: Dict[str, int] = {}
    total_ui_elements = 0
    total_actionable_elements = 0
    total_feedback_elements = 0
    failed_items: List[str] = []
    failed_extractions_count = 0

    validation_reports: List[Dict[str, Any]] = []
    vision_call_count = 0
    invalid_intent_ref_total = 0
    invalid_group_ref_total = 0

    ui_pkg_id = f"ui_pkg_{uuid.uuid4().hex[:12]}"
    sip_pkg_id = f"sbi_pkg_{uuid.uuid4().hex[:12]}"

    for img in ordered_images:
        if not img.storage_uri:
            warnings.append(f"Image {img.id} missing storage_uri. Skipped.")
            failed_extractions_count += 1
            failed_items.append(img.id)
            continue

        response = next(vision_iter)
        vision_call_count += 1

        if isinstance(response, Exception):
            logger.error(
                "Joint understanding failed for image %s: %s",
                img.id,
                response,
                exc_info=(type(response), response, response.__traceback__),
            )
            failed_extractions_count += 1
            failed_items.append(img.id)
            db.add(
                UIState(
                    id=generate_state_id_for_image(img),
                    run_id=run_id,
                    image_id=img.id,
                    page_type="unknown_page",
                    extraction_status="failed",
                    extraction_error=str(response),
                )
            )
            await db.commit()
            continue

        if response.status.value != "success" or not response.parsed_output:
            err = getattr(response, "error", None) or "unknown error"
            logger.error("Joint understanding provider failure for image %s: %s", img.id, err)
            failed_extractions_count += 1
            failed_items.append(img.id)
            db.add(
                UIState(
                    id=generate_state_id_for_image(img),
                    run_id=run_id,
                    image_id=img.id,
                    page_type="unknown_page",
                    extraction_status="failed",
                    extraction_error=str(err),
                )
            )
            await db.commit()
            continue

        joint: JointScreenUnderstandingResult = response.parsed_output
        ui_raw = joint.ui_state.model_copy(deep=True)
        intents_raw = joint.screen_intents.model_copy(deep=True)

        try:
            state_row, counts = persist_ui_state_from_v2_result(db, run_id, img, ui_raw)
            extracted_states.append(state_row)

            canonical_screen_type = state_row["screen_type"]
            page_type_distribution[canonical_screen_type] = page_type_distribution.get(
                canonical_screen_type, 0
            ) + 1
            total_ui_elements += counts["total_ui_elements"]
            total_actionable_elements += counts["total_actionable_elements"]
            total_feedback_elements += counts["total_feedback_elements"]

            intents_prefixed = prefix_screen_intent_payload(state_row["state_id"], intents_raw)
            draft_dump = intents_prefixed.model_dump(mode="python")
            val_rep = validate_joint_screen_understanding_structured(state_row, draft_dump)
            validation_reports.append(
                {
                    "state_id": state_row["state_id"],
                    "duplicate_element_ids": val_rep.duplicate_element_ids,
                    "duplicate_action_ids": val_rep.duplicate_action_ids,
                    "duplicate_feedback_ids": val_rep.duplicate_feedback_ids,
                    "duplicate_group_ids": val_rep.duplicate_group_ids,
                    "orphan_elements": val_rep.orphan_elements_not_in_any_group,
                    "invalid_ref_total": val_rep.invalid_ref_total,
                    "warnings": val_rep.warnings,
                }
            )
            invalid_intent_ref_total += val_rep.invalid_ref_total
            invalid_group_ref_total += (
                val_rep.invalid_intent_group_refs + val_rep.duplicate_group_ids
            )

            cat, unst, summary, _ = process_screen_intents_for_state(
                state_row, intents_prefixed, generate_screen_intent_id
            )
            per_state_summaries.append(summary)
            merged_unresolved.extend(unst)

            draft_raw_outer = intents_prefixed.model_dump(mode="python")
            screen_intent_catalog.extend(cat)
            persist_screen_intent_catalog_rows(db, run_id, state_row["state_id"], cat, draft_raw_outer)

            await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Joint understanding persistence failed for image %s: %s", img.id, exc)
            await db.rollback()
            warnings.append(f"Joint persistence failed for image {img.id}: {exc}")
            failed_extractions_count += 1
            failed_items.append(img.id)

    extracted_states_count = len(extracted_states)

    ui_report = {
        "run_id": run_id,
        "ui_state_package_id": ui_pkg_id,
        "extraction_mode": "joint",
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

    total_val = sum(s.get("validated_intents", 0) for s in per_state_summaries)
    agg_unres: Dict[str, int] = {}
    for s in per_state_summaries:
        for k, v in (s.get("unresolved_reason_counts") or {}).items():
            agg_unres[k] = agg_unres.get(k, 0) + v

    intent_validation_summary = {
        "per_state": per_state_summaries,
        "aggregate_validated_intents": total_val,
        "aggregate_unresolved_reason_codes": agg_unres,
        "skipped_state_count": 0,
    }

    sip_report = {
        "run_id": run_id,
        "screen_intent_package_id": sip_pkg_id,
        "extraction_mode": "joint",
        "total_states_processed": extracted_states_count,
        "total_intents_extracted": total_val,
        "failed_states": failed_extractions_count,
        "warnings": warnings,
        "skipped_states": [],
    }

    duration_ms = int((time.time() - start_time) * 1000)
    input_image_count = len(images_for_vision)
    legacy_calls = input_image_count * 2
    saved_calls = max(0, legacy_calls - vision_call_count)
    saved_rate = (saved_calls / legacy_calls) if legacy_calls else 0.0

    ig_count = sum(len(s.get("interaction_groups") or []) for s in extracted_states)
    joint_metrics = {
        "input_image_count": input_image_count,
        "vision_call_count": vision_call_count,
        "legacy_estimated_call_count": legacy_calls,
        "saved_llm_call_count": saved_calls,
        "saved_call_rate": round(saved_rate, 4),
        "extracted_state_count": extracted_states_count,
        "extracted_interaction_group_count": ig_count,
        "extracted_intent_count": len(screen_intent_catalog),
        "unresolved_screen_group_count": len(merged_unresolved),
        "invalid_intent_ref_count": invalid_intent_ref_total,
        "invalid_group_ref_count": invalid_group_ref_total,
        "joint_output_validation_pass_rate": (
            1.0
            if extracted_states_count == 0
            else max(
                0.0,
                1.0 - (invalid_intent_ref_total / max(1, extracted_states_count)),
            )
        ),
        "duration_ms": duration_ms,
        "avg_duration_ms_per_image": (
            round(duration_ms / vision_call_count, 2) if vision_call_count else 0
        ),
        "validation_reports": validation_reports,
    }

    joint_report_artifact = {
        "run_id": run_id,
        "schema_version": "1.0",
        "agent_name": "joint_screen_understanding_agent",
        "input_image_count": input_image_count,
        "extracted_states_count": extracted_states_count,
        "extracted_intents_count": len(screen_intent_catalog),
        "unresolved_screen_groups_count": len(merged_unresolved),
        "failed_images_count": failed_extractions_count,
        "call_reduction_estimate": {
            "legacy_calls": legacy_calls,
            "joint_calls": vision_call_count,
            "saved_calls": saved_calls,
        },
        "validation_summary": validation_reports,
        "joint_screen_understanding_metrics": joint_metrics,
    }

    if settings.SAVE_JOINT_SCREEN_UNDERSTANDING_REPORT:
        report_bytes = json.dumps(joint_report_artifact, indent=2).encode("utf-8")
        report_key = f"artifacts/{run_id}/joint_screen_understanding/joint_screen_understanding_report.json"
        report_uri = storage_service.upload_file(report_bytes, report_key, content_type="application/json")
        db.add(
            Artifact(
                id=_artifact_id(),
                run_id=run_id,
                artifact_type="joint_screen_understanding_report",
                node_name="joint_screen_understanding",
                storage_uri=report_uri,
                metadata_json={"extracted_states_count": extracted_states_count},
            )
        )
        await db.commit()

    log_event("joint_screen_understanding_completed", run_id=run_id, duration_ms=duration_ms)

    ui_pkg = {
        "schema_version": "1.0",
        "agent_name": "joint_screen_understanding_agent",
        "extraction_mode": "joint",
        "ui_state_package_id": ui_pkg_id,
        "extracted_states": extracted_states,
        "state_catalog": extracted_states,
        "interaction_group_catalog": [
            {**ig, "source_state_id": state["state_id"]}
            for state in extracted_states
            for ig in state.get("interaction_groups", [])
        ],
        "report": ui_report,
    }
    sip_pkg = {
        "schema_version": "2.1",
        "agent_name": "joint_screen_understanding_agent",
        "extraction_mode": "joint",
        "screen_intent_package_id": sip_pkg_id,
        "screen_intent_catalog": screen_intent_catalog,
        "unresolved_screen_groups": merged_unresolved,
        "skipped_states": [],
        "intent_validation_summary": intent_validation_summary,
        "report": sip_report,
    }

    return {
        "ui_state_package": ui_pkg,
        "state_catalog": extracted_states,
        "interaction_group_catalog": ui_pkg["interaction_group_catalog"],
        "screen_intent_package": sip_pkg,
        "report": joint_report_artifact,
        "metrics": {"joint_screen_understanding_metrics": joint_metrics},
    }
