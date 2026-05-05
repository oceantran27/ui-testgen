"""Parse UI extraction JSON from stage-1 model output."""

from __future__ import annotations

import json

from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.ui_extraction import UIExtractionResult


def parse_ui_extraction_payload(raw: str) -> UIExtractionResult:
    minified = extract_and_minify_json(raw)
    if not minified:
        raise AIProcessingError("Could not parse UI extraction JSON from model output")
    try:
        data = json.loads(minified)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Invalid UI extraction JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIProcessingError("UI extraction output must be a JSON object")
    try:
        return UIExtractionResult.model_validate(data)
    except Exception as exc:
        raise AIProcessingError(f"Invalid UI extraction payload shape: {exc}") from exc


def ui_extraction_to_minified_json(result: UIExtractionResult) -> str:
    """Stable JSON string for downstream text-only stages."""
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
