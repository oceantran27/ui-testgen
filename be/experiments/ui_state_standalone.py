"""
Standalone Phase 6 (UI State Understanding) — preprocess a folder of screenshots, then run
structured VLM extraction (same prompts/schema as production). Writes one combined JSON report.

Run from the ``be/`` directory::

    cd be
    python experiments/ui_state_standalone.py

Requirements:
- ``STORAGE_*`` / MinIO (or S3-compatible) per ``app.core.config`` (normalize uploads during preprocess).
- Model provider credentials / ``MOCK_MODEL_MODE`` per ``app.core.config`` and ``be/docs/ENVIRONMENT.md``.

Edit ``INPUT_IMAGES_DIR`` below to point at a folder of screenshots (png / jpg / jpeg / webp).
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── User: set your input folder here (raw string path on Windows is fine) ──
INPUT_IMAGES_DIR: Path = Path(r"C:\Users\daidu\Desktop\flow\shopee")

OUTPUT_JSON_PATH: Path = Path(__file__).resolve().parent / "ui_state_standalone_output.json"

SYSTEM_INSTRUCTION_UI_STATE = (
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

USER_INSTRUCTION_UI_STATE = (
    "Analyze this screenshot and extract the UI state. Identify the page type, visible texts, "
    "and all significant UI elements. Determine if they are actionable or feedback elements."
)


def _be_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_sys_path() -> None:
    root = str(_be_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _suffix_to_format(suffix: str) -> str | None:
    s = suffix.lower().lstrip(".")
    if s == "jpeg":
        return "jpg"
    if s in ("png", "jpg", "webp"):
        return s
    return None


def _coerce_ui_result(
    parsed: Any,
    schema: type,
) -> Any:
    """Normalize provider output to the Pydantic model (dict or instance)."""
    if isinstance(parsed, schema):
        return parsed
    return schema.model_validate(parsed)


def _error_payload(err: Any) -> Optional[Dict[str, Any]]:
    if err is None:
        return None
    return {
        "error_code": getattr(err, "error_code", str(type(err).__name__)),
        "message": getattr(err, "message", str(err)),
        "provider": getattr(err, "provider", None),
        "retryable": getattr(err, "retryable", None),
    }


async def main_async() -> None:
    _ensure_sys_path()

    from app.core.config import settings
    from app.model_providers import model_adapter
    from app.model_providers.base import ImageInput, NonRetryableModelError
    from app.model_providers.schemas import UIStateExtractionResult
    from app.services.preprocessing_service import (
        build_quality_report,
        run_preprocessing_pipeline_on_bytes,
        viewport_bands_from_settings,
    )
    from app.services.ui_state_service import (
        _convert_bbox,
        _generate_state_id,
        _generate_state_signature,
    )

    input_dir = INPUT_IMAGES_DIR.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"INPUT_IMAGES_DIR is not a directory: {input_dir}")

    allowed = {x.lower() for x in settings.ALLOWED_IMAGE_FORMATS}
    files: list[Path] = []
    for p in sorted(input_dir.iterdir()):
        if not p.is_file():
            continue
        fmt = _suffix_to_format(p.suffix)
        if fmt and fmt in allowed:
            files.append(p)

    if not files:
        raise SystemExit(
            f"No images with extensions {sorted(allowed)} found under {input_dir}"
        )

    synthetic_run_id = f"exp_uistate_{uuid.uuid4().hex[:10]}"
    bands = viewport_bands_from_settings()

    per_image: list[dict[str, Any]] = []
    for idx, path in enumerate(files):
        raw = path.read_bytes()
        image_id = f"exp_{path.stem}_{idx}"
        fmt = _suffix_to_format(path.suffix)
        assert fmt is not None
        row: dict[str, Any] = run_preprocessing_pipeline_on_bytes(
            raw,
            image_id=image_id,
            original_filename=path.name,
            metadata_format=fmt,
            run_id=synthetic_run_id,
            bands=bands,
        )
        row["source_path"] = str(path)
        per_image.append(row)

    aggregate = build_quality_report(synthetic_run_id, per_image)

    state_catalog: List[Dict[str, Any]] = []
    extracted_states_count = 0
    failed_extractions_count = 0
    page_type_distribution: Dict[str, int] = {}
    total_ui_elements = 0
    total_actionable_elements = 0
    total_feedback_elements = 0
    failed_items: List[str] = []
    warnings: List[str] = []
    extraction_per_image: List[Dict[str, Any]] = []
    state_ids: List[str] = []

    for row in per_image:
        image_id = row["image_id"]
        base_entry: Dict[str, Any] = {
            "image_id": image_id,
            "source_path": row.get("source_path"),
            "preprocess_is_valid": row.get("is_valid"),
            "normalized_uri": row.get("normalized_uri"),
        }

        if not row.get("is_valid") or not row.get("normalized_uri"):
            reason = []
            if not row.get("is_valid"):
                reason.append("preprocess_not_valid")
            if not row.get("normalized_uri"):
                reason.append("missing_normalized_uri")
            warnings.append(
                f"Image {image_id} skipped for UI state extraction ({', '.join(reason)})."
            )
            failed_extractions_count += 1
            failed_items.append(image_id)
            extraction_per_image.append(
                {
                    **base_entry,
                    "extraction_status": "skipped",
                    "skip_reason": reason,
                    "model_response_status": None,
                    "model_error": None,
                }
            )
            continue

        image_input = ImageInput(image_id=image_id, storage_uri=row["normalized_uri"])
        try:
            response = await model_adapter.call_vision_structured(
                task_name="ui_state_extraction",
                run_id=synthetic_run_id,
                node_name="ui_state_extraction_node",
                system_instruction=SYSTEM_INSTRUCTION_UI_STATE,
                user_instruction=USER_INSTRUCTION_UI_STATE,
                image_inputs=[image_input],
                output_schema=UIStateExtractionResult,
                prompt_name="ui_state_extraction_prompt",
                prompt_version="v1",
            )
        except NonRetryableModelError as e:
            failed_extractions_count += 1
            failed_items.append(image_id)
            extraction_per_image.append(
                {
                    **base_entry,
                    "extraction_status": "failed",
                    "model_response_status": None,
                    "model_error": _error_payload(e.error),
                    "note": "non_retryable_after_all_retries",
                }
            )
            continue

        ok = response.status.value == "success" and response.parsed_output is not None
        if not ok:
            failed_extractions_count += 1
            failed_items.append(image_id)
            extraction_per_image.append(
                {
                    **base_entry,
                    "extraction_status": "failed",
                    "model_response_status": response.status.value,
                    "model_error": _error_payload(response.error),
                    "latency_ms": response.latency_ms,
                }
            )
            continue

        result_data: UIStateExtractionResult = _coerce_ui_result(
            response.parsed_output,
            UIStateExtractionResult,
        )
        state_id = _generate_state_id()
        state_ids.append(state_id)

        conf_label = "low"
        if result_data.confidence >= 0.85:
            conf_label = "high"
        elif result_data.confidence >= 0.65:
            conf_label = "medium"

        signature = _generate_state_signature(result_data.page_type, result_data.ui_elements)

        actionable_count = 0
        feedback_count = 0
        elements_out: List[Dict[str, Any]] = []
        for el_data in result_data.ui_elements:
            bbox = _convert_bbox(el_data.bbox_ymin_xmin_ymax_xmax)
            elements_out.append(
                {
                    "type": el_data.type,
                    "label": el_data.label,
                    "text": el_data.text,
                    "placeholder": el_data.placeholder,
                    "bbox": bbox,
                    "actionable": el_data.actionable,
                    "action_type": el_data.action_type,
                    "is_feedback": el_data.is_feedback,
                    "feedback_type": el_data.feedback_type,
                    "confidence": el_data.confidence,
                }
            )
            if el_data.actionable:
                actionable_count += 1
                total_actionable_elements += 1
            if el_data.is_feedback:
                feedback_count += 1
                total_feedback_elements += 1

        total_ui_elements += len(result_data.ui_elements)
        extracted_states_count += 1
        page_type_distribution[result_data.page_type] = (
            page_type_distribution.get(result_data.page_type, 0) + 1
        )

        if result_data.warnings:
            warnings.extend([f"[{image_id}] {w}" for w in result_data.warnings])

        state_catalog.append(
            {
                "state_id": state_id,
                "image_id": image_id,
                "page_type": result_data.page_type,
                "state_summary": result_data.state_summary,
                "state_signature": signature,
                "visible_texts": result_data.visible_texts[:10],
                "element_count": len(result_data.ui_elements),
                "actionable_element_count": actionable_count,
                "feedback_element_count": feedback_count,
                "confidence": result_data.confidence,
            }
        )

        extraction_per_image.append(
            {
                **base_entry,
                "extraction_status": "success",
                "state_id": state_id,
                "state_signature": signature,
                "confidence_label": conf_label,
                "model_response_status": response.status.value,
                "latency_ms": response.latency_ms,
                "parsed": result_data.model_dump(),
                "ui_elements_normalized_bbox": elements_out,
            }
        )

    report = {
        "run_id": synthetic_run_id,
        "canonical_images_count": len(per_image),
        "extracted_states_count": extracted_states_count,
        "failed_extractions_count": failed_extractions_count,
        "state_ids": state_ids,
        "page_type_distribution": page_type_distribution,
        "total_ui_elements": total_ui_elements,
        "total_actionable_elements": total_actionable_elements,
        "total_feedback_elements": total_feedback_elements,
        "failed_items": failed_items,
        "warnings": warnings,
    }

    out = {
        "run_id": synthetic_run_id,
        "input_dir": str(input_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "settings_snapshot": {
            "USE_VLM_FOR_UI_STATE_EXTRACTION": settings.USE_VLM_FOR_UI_STATE_EXTRACTION,
            "MOCK_MODEL_MODE": settings.MOCK_MODEL_MODE,
            "VISION_MODEL_TIMEOUT_SECONDS": settings.VISION_MODEL_TIMEOUT_SECONDS,
            "UI_STATE_EXTRACTION_MAX_OUTPUT_TOKENS": settings.UI_STATE_EXTRACTION_MAX_OUTPUT_TOKENS,
        },
        "viewport_constraints": {
            "short_edge_min": bands.short_edge_min,
            "short_edge_max": bands.short_edge_max,
            "long_edge_min": bands.long_edge_min,
            "long_edge_max": bands.long_edge_max,
            "aspect_ratio_min": bands.aspect_ratio_min,
            "aspect_ratio_max": bands.aspect_ratio_max,
        },
        "preprocessing": {
            "aggregate": aggregate,
            "per_image": per_image,
        },
        "ui_state_extraction": {
            "state_catalog": state_catalog,
            "report": report,
            "per_image": extraction_per_image,
        },
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(
        f"Wrote {OUTPUT_JSON_PATH} ({len(per_image)} images, "
        f"{extracted_states_count} UI states extracted, {failed_extractions_count} VLM failures)"
    )


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
