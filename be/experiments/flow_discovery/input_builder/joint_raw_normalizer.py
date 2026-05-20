"""Normalize heterogeneous joint raw JSON into ui_state + screen_intents dicts."""

from __future__ import annotations

import json
from typing import Any

from experiments.flow_discovery.schemas.input_builder_schema import JointRawFileRecord, NormalizedJointOutput


def _extract_payload(record: JointRawFileRecord) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    payload = dict(record.raw_payload)
    ui: dict[str, Any] | None = None
    si: dict[str, Any] | None = None

    # Shape B — provider wrapper
    if isinstance(payload.get("parsed_output"), dict):
        inner = payload["parsed_output"]
        ui = inner.get("ui_state") if isinstance(inner.get("ui_state"), dict) else None
        si = inner.get("screen_intents") if isinstance(inner.get("screen_intents"), dict) else None
        if ui is not None or si is not None:
            return ui, si, warnings

    # Shape C — nested output
    if isinstance(payload.get("output"), dict):
        inner = payload["output"]
        ui = inner.get("ui_state") if isinstance(inner.get("ui_state"), dict) else None
        si = inner.get("screen_intents") if isinstance(inner.get("screen_intents"), dict) else None
        if ui is not None or si is not None:
            return ui, si, warnings

    # Shape D — raw_text JSON
    raw_text = payload.get("raw_text")
    if isinstance(raw_text, str) and raw_text.strip():
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            warnings.append("RAW_TEXT_JSON_PARSE_FAILED")
            parsed = None
        if isinstance(parsed, dict):
            ui = parsed.get("ui_state") if isinstance(parsed.get("ui_state"), dict) else None
            si = parsed.get("screen_intents") if isinstance(parsed.get("screen_intents"), dict) else None
            if ui is not None or si is not None:
                return ui, si, warnings

    # Shape A — direct
    ui = payload.get("ui_state") if isinstance(payload.get("ui_state"), dict) else None
    si = payload.get("screen_intents") if isinstance(payload.get("screen_intents"), dict) else None
    return ui, si, warnings


class JointRawNormalizer:
    def normalize(self, record: JointRawFileRecord, *, strict: bool = False) -> NormalizedJointOutput:
        ui, si, warnings = _extract_payload(record)
        out_warnings = list(warnings)
        if ui is None:
            out_warnings.append("MISSING_UI_STATE")
            ui = {}
        if si is None:
            out_warnings.append("MISSING_SCREEN_INTENTS")
            si = {}
        if ("MISSING_UI_STATE" in out_warnings or "MISSING_SCREEN_INTENTS" in out_warnings) and strict:
            raise ValueError("MISSING_UI_STATE_OR_SCREEN_INTENTS")
        if "MISSING_UI_STATE" in out_warnings or "MISSING_SCREEN_INTENTS" in out_warnings:
            out_warnings.append("MISSING_UI_STATE_OR_SCREEN_INTENTS")
        return NormalizedJointOutput(
            source_image_id=record.source_image_id,
            raw_file_name=record.raw_file_name,
            ui_state=ui,
            screen_intents=si,
            warnings=out_warnings,
        )


__all__ = ["JointRawNormalizer"]
