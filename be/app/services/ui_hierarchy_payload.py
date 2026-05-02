"""Parse UI hierarchy JSON from Agent 1 model output."""

from __future__ import annotations

import json
from typing import Any

from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.ui_hierarchy import UiHierarchyExtractionResult, UiHierarchyNode


def parse_ui_hierarchy_payload(raw: str) -> UiHierarchyExtractionResult:
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
        return UiHierarchyExtractionResult.model_validate(data)
    except Exception as exc:
        raise AIProcessingError(f"Invalid UI hierarchy payload shape: {exc}") from exc


def ui_hierarchy_to_minified_json(result: UiHierarchyExtractionResult) -> str:
    """Stable JSON string for Agent 2 user payload."""
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


def count_control_nodes(node: UiHierarchyNode) -> int:
    n = 1 if (node.kind or "").lower() == "control" else 0
    return n + sum(count_control_nodes(ch) for ch in node.children)


def collect_verbatim_literals_from_dump(obj: Any, out: set[str]) -> None:
    """Gather strings usable as Gherkin literals from a dumped hierarchy dict."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in (
                "verbatim_label_for_steps",
                "visible_text",
                "first_visible_item_literal",
                "destination_phrase_verbatim",
            ) and isinstance(val, str) and val.strip():
                out.add(val)
            elif key == "peer_nav_labels_sample" and isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        out.add(item)
            else:
                collect_verbatim_literals_from_dump(val, out)
    elif isinstance(obj, list):
        for item in obj:
            collect_verbatim_literals_from_dump(item, out)
