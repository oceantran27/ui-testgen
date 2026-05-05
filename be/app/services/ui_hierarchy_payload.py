"""Parse UI hierarchy JSON from Agent 1 model output."""

from __future__ import annotations

import json

from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.ui_hierarchy import UIHierarchyResult


def parse_ui_hierarchy_payload(raw: str) -> UIHierarchyResult:
    minified = extract_and_minify_json(raw)
    if not minified:
        raise AIProcessingError("Could not parse UI hierarchy JSON from model output")
    try:
        data = json.loads(minified)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Invalid UI hierarchy JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIProcessingError("UI hierarchy output must be a JSON object")
    try:
        return UIHierarchyResult.model_validate(data)
    except Exception as exc:
        raise AIProcessingError(f"Invalid UI hierarchy payload shape: {exc}") from exc


def ui_hierarchy_to_minified_json(result: UIHierarchyResult) -> str:
    """Stable JSON string for Agent 2 user payload."""
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
