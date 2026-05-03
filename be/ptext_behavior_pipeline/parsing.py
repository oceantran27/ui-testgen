"""JSON parsing helpers for Stage C bundle and Stage A behavior-flow array."""

from __future__ import annotations

import json
import re

from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.behavior_flow import BehaviorFlowItem

from ptext_behavior_pipeline.schemas import BddBundlePtext

_IMG_ID_RE = re.compile(r"^img_(\d{3})$")


def parse_bdd_bundle_ptext(raw: str) -> BddBundlePtext:
    minified = extract_and_minify_json(raw)
    if not minified:
        raise AIProcessingError("Could not parse BDD bundle JSON from model output")
    try:
        data = json.loads(minified)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Invalid BDD bundle JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIProcessingError("BDD bundle output must be a JSON object")
    try:
        return BddBundlePtext.model_validate(data)
    except Exception as exc:
        raise AIProcessingError(f"Invalid BDD bundle payload shape: {exc}") from exc


def parse_json_array_loose(raw: str) -> list[object]:
    """Parse model output to a list; mirrors behavior_flow_cluster_service."""
    minified = extract_and_minify_json(raw)
    if minified:
        try:
            parsed = json.loads(minified)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    s = raw.strip()
    start = s.find("[")
    if start == -1:
        raise AIProcessingError("Could not find JSON array in model output")
    depth = 0
    in_str = False
    esc = False
    for idx in range(start, len(s)):
        ch = s[idx]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    chunk = s[start : idx + 1]
                    return json.loads(chunk)
    raise AIProcessingError("Unbalanced or invalid JSON array in model output")


def validate_behavior_flow_partition(expected: set[str], items: list[BehaviorFlowItem]) -> None:
    seen: set[str] = set()
    for it in items:
        for sid in it.screens:
            if sid not in expected:
                raise AIProcessingError(f"Invalid or unknown capture id in output: {sid!r}")
            if _IMG_ID_RE.match(sid) is None:
                raise AIProcessingError(f"Capture id must match img_###: {sid!r}")
            if sid in seen:
                raise AIProcessingError(f"Duplicate capture id in output: {sid!r}")
            seen.add(sid)
    if seen != expected:
        missing = expected - seen
        extra = seen - expected
        raise AIProcessingError(
            f"Capture id partition mismatch: missing={sorted(missing)} extra={sorted(extra)}"
        )


def parse_behavior_flow_stage_a(raw: str, *, expected_ids: list[str]) -> list[BehaviorFlowItem]:
    """Parse Stage A JSON: either `{\"flows\":[...]} ` or a bare array (fallback)."""
    minified = extract_and_minify_json(raw)
    if minified:
        try:
            outer = json.loads(minified)
        except json.JSONDecodeError:
            outer = None
        if outer is not None:
            data: list[object] | None
            if isinstance(outer, dict) and isinstance(outer.get("flows"), list):
                data = outer["flows"]
            elif isinstance(outer, list):
                data = outer
            else:
                data = None
            if isinstance(data, list) and data:
                items = [BehaviorFlowItem.model_validate(row) for row in data]
                validate_behavior_flow_partition(set(expected_ids), items)
                return items

    data = parse_json_array_loose(raw)
    if not isinstance(data, list) or not data:
        raise AIProcessingError("Model output must be a non-empty flows array")
    items = []
    for row in data:
        try:
            items.append(BehaviorFlowItem.model_validate(row))
        except Exception as exc:
            raise AIProcessingError(f"Invalid behavior flow item shape: {exc}") from exc
    validate_behavior_flow_partition(set(expected_ids), items)
    return items
