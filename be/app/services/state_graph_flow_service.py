"""Infer cross-screen flows from per-screen intents using Gemini or OpenAI (text-only)."""

from __future__ import annotations

import json
import logging
from typing import Any

from google.genai import types
from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.state_graph import StateGraphFlowItem
from app.services.gemini_genai_client import default_generate_config, get_gemini_client
from app.services.prompt_service import load_state_graph_from_intents_prompt

logger = logging.getLogger(__name__)


def _flow_model_uses_openai(model_id: str) -> bool:
    return model_id.strip().lower().startswith("gpt-")


def _parse_flows_object(raw: str) -> dict[str, Any]:
    m = extract_and_minify_json(raw)
    if not m:
        raise AIProcessingError("Could not parse state-graph JSON from model output")
    try:
        data = json.loads(m)
    except json.JSONDecodeError as exc:
        raise AIProcessingError(f"Invalid state-graph JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AIProcessingError("State graph output must be a JSON object")
    flows = data.get("flows")
    if not isinstance(flows, list):
        raise AIProcessingError("State graph JSON must contain a 'flows' array")
    return data


def _dedupe_consecutive(nodes: list[str]) -> list[str]:
    out: list[str] = []
    for n in nodes:
        if not out or out[-1] != n:
            out.append(n)
    return out


def normalize_and_complete_flows(
    known_image_ids: set[str],
    flows: list[StateGraphFlowItem],
) -> list[StateGraphFlowItem]:
    """
    - Drop unknown node ids; dedupe consecutive duplicates.
    - Remove flows with no nodes after filtering.
    - Add singleton flows for any known_image_ids not covered by any flow.
    """
    covered: set[str] = set()
    cleaned: list[StateGraphFlowItem] = []

    for fl in flows:
        nodes = [n for n in fl.nodes if n in known_image_ids]
        nodes = _dedupe_consecutive(nodes)
        if not nodes:
            continue
        cleaned.append(StateGraphFlowItem(id=fl.id, name=fl.name, nodes=nodes))
        covered.update(nodes)

    missing = sorted(known_image_ids - covered)
    for mid in missing:
        cleaned.append(
            StateGraphFlowItem(
                id=f"standalone-{mid[:16]}",
                name="Standalone screen",
                nodes=[mid],
            )
        )

    if not cleaned and known_image_ids:
        # Model returned nothing usable — one flow per screen
        for mid in sorted(known_image_ids):
            cleaned.append(
                StateGraphFlowItem(
                    id=f"standalone-{mid[:16]}",
                    name="Standalone screen",
                    nodes=[mid],
                )
            )

    return cleaned


def _fallback_singleton_flows(image_ids: set[str]) -> list[StateGraphFlowItem]:
    out: list[StateGraphFlowItem] = []
    for mid in sorted(image_ids):
        out.append(
            StateGraphFlowItem(
                id=f"standalone-{mid[:16]}",
                name="Standalone screen",
                nodes=[mid],
            )
        )
    return out


def _build_state_graph_user_text(screens_payload: dict[str, Any]) -> str:
    return (
        "Input JSON has a top-level \"screens\" array. Each element MUST have been built with "
        "keys: image_id, ui_state_type, primary_heading, page_summary, navigational_destinations, "
        "user_intents. Infer ordered flows per system instructions. Return ONLY raw JSON with a "
        "\"flows\" array.\n"
        f"{json.dumps(screens_payload, ensure_ascii=False)}"
    )


def _content_to_flow_items(content: str, fallback_image_ids: set[str]) -> list[StateGraphFlowItem]:
    if not content.strip():
        logger.warning("Empty state-graph response; using fallback singleton flows.")
        return _fallback_singleton_flows(fallback_image_ids)

    try:
        data = _parse_flows_object(content)
    except AIProcessingError as exc:
        logger.warning("Parse state-graph failed (%s); using fallback singleton flows.", exc)
        return _fallback_singleton_flows(fallback_image_ids)

    raw_flows = data.get("flows") or []
    items: list[StateGraphFlowItem] = []
    for i, x in enumerate(raw_flows):
        if not isinstance(x, dict):
            continue
        fid = str(x.get("id") or "").strip() or f"flow-{i+1:03d}"
        name = str(x.get("name") or "").strip() or f"Flow {i+1}"
        nodes_raw = x.get("nodes")
        if not isinstance(nodes_raw, list):
            continue
        nodes = [str(n).strip() for n in nodes_raw if str(n).strip()]
        if not nodes:
            continue
        items.append(StateGraphFlowItem(id=fid, name=name, nodes=nodes))

    if not items:
        logger.warning("Model returned no valid flows; using fallback singleton flows.")
        return _fallback_singleton_flows(fallback_image_ids)

    return items


def run_state_graph_gemini_sync(
    screens_payload: dict[str, Any],
    gemini_model: str,
    *,
    fallback_image_ids: set[str],
) -> list[StateGraphFlowItem]:
    """Call Gemini with bundled screen metadata + intents; return parsed flows (not yet normalized)."""
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")

    system_prompt = load_state_graph_from_intents_prompt()
    user_text = _build_state_graph_user_text(screens_payload)

    client = get_gemini_client()
    try:
        response = client.models.generate_content(
            model=gemini_model,
            contents=[types.Part.from_text(text=user_text)],
            config=default_generate_config(system_instruction=system_prompt),
        )
    except Exception as exc:
        logger.error("Gemini state-graph inference failed: %s", exc)
        raise AIProcessingError(f"State graph inference failed: {exc}") from exc

    content = getattr(response, "text", None) or ""
    return _content_to_flow_items(content, fallback_image_ids)


def run_state_graph_openai_sync(
    screens_payload: dict[str, Any],
    openai_model: str,
    *,
    fallback_image_ids: set[str],
) -> list[StateGraphFlowItem]:
    """Call OpenAI with the same bundle + system prompt as Gemini flow stage."""
    if not settings.OPENAI_API_KEY:
        raise AIProcessingError("OPENAI_API_KEY is not configured")

    system_prompt = load_state_graph_from_intents_prompt()
    user_text = _build_state_graph_user_text(screens_payload)
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model=openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.error("OpenAI state-graph inference failed: %s", exc)
        raise AIProcessingError(f"State graph inference failed: {exc}") from exc

    message = response.choices[0].message.content
    content = message if message else ""
    return _content_to_flow_items(content, fallback_image_ids)


def run_state_graph_flow_sync(
    screens_payload: dict[str, Any],
    model: str,
    *,
    fallback_image_ids: set[str],
) -> list[StateGraphFlowItem]:
    """Dispatch to Gemini or OpenAI based on ``model`` id (e.g. ``gpt-`` prefix → OpenAI)."""
    if _flow_model_uses_openai(model):
        return run_state_graph_openai_sync(
            screens_payload, model, fallback_image_ids=fallback_image_ids
        )
    return run_state_graph_gemini_sync(
        screens_payload, model, fallback_image_ids=fallback_image_ids
    )
