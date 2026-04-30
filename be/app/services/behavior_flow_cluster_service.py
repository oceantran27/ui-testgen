import asyncio
import json
import logging
import re
from typing import Any

from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.modules.vision_extractor.json_processor import extract_and_minify_json
from app.schemas.behavior_flow import BehaviorFlowItem, BehaviorFlowOrganizeResponse
from app.services.gemini_genai_client import default_generate_config, get_gemini_client, pil_image_to_part
from app.services.prompt_service import load_behavior_flow_cluster_prompt

logger = logging.getLogger(__name__)

BEHAVIOR_FLOW_MODEL = "gemini-2.5-flash"
_IMG_ID_RE = re.compile(r"^img_(\d{3})$")


def _ensure_rgb_rgba(pil: Image.Image) -> Image.Image:
    if pil.mode in ("RGB", "L"):
        if pil.mode == "L":
            return pil.convert("RGB")
        return pil
    if pil.mode in ("RGBA", "P", "PA"):
        if pil.mode == "P" or pil.mode == "PA":
            pil = pil.convert("RGBA")
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[-1] if pil.mode == "RGBA" else None)
        return bg
    return pil.convert("RGB")


def _resize_max_edge(pil: Image.Image, max_edge: int) -> Image.Image:
    if max_edge <= 0:
        return pil
    w, h = pil.size
    m = max(w, h)
    if m <= max_edge:
        return pil
    r = max_edge / m
    new_w, new_h = max(1, int(w * r)), max(1, int(h * r))
    return pil.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _load_image_for_model(path: str) -> Image.Image:
    try:
        img = Image.open(path)
    except Exception as exc:
        logger.error("Failed to open image: %s: %s", path, exc)
        raise AIProcessingError(f"Failed to read image file: {exc}") from exc
    return _resize_max_edge(_ensure_rgb_rgba(img), settings.BEHAVIOR_FLOW_MAX_IMAGE_EDGE)


def _parse_json_array_loose(raw: str) -> Any:
    """Parse model output to a list; try extract_and_minify_json, then first balanced top-level array."""
    m = extract_and_minify_json(raw)
    if m:
        try:
            parsed = json.loads(m)
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


def _expected_ids(n: int) -> list[str]:
    return [f"img_{i:03d}" for i in range(1, n + 1)]


def _validate_partition(expected: set[str], items: list[BehaviorFlowItem]) -> None:
    seen: set[str] = set()
    for it in items:
        for sid in it.screens:
            if sid not in expected:
                raise AIProcessingError(f"Invalid or unknown screen id in output: {sid!r}")
            if _IMG_ID_RE.match(sid) is None:
                raise AIProcessingError(f"Screen id must match img_###: {sid!r}")
            if sid in seen:
                raise AIProcessingError(f"Duplicate screen id in output: {sid!r}")
            seen.add(sid)
    if seen != expected:
        missing = expected - seen
        extra = seen - expected
        raise AIProcessingError(
            f"Screen id partition mismatch: missing={sorted(missing)} extra={sorted(extra)}"
        )


def _run_gemini_cluster_sync(
    image_ids: list[str],
    image_paths: list[str],
) -> list[BehaviorFlowItem]:
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    if len(image_ids) != len(image_paths) or not image_ids:
        raise AIProcessingError("image_ids and image_paths must be non-empty and same length")

    system_prompt = load_behavior_flow_cluster_prompt()
    order_lines = "\n".join(f"- {eid} — image {i} in the sequence below" for i, eid in enumerate(image_ids, start=1))
    user_text = (
        f"You are given {len(image_ids)} images in this exact order. IDs (for output only) are:\n{order_lines}\n\n"
        "The images in the next message content follow the same order as listed (first image = first ID in the list). "
        "Return only the required JSON array as specified in the system instructions."
    )

    client = get_gemini_client()
    parts: list[Any] = [types.Part.from_text(text=user_text)]
    for p in image_paths:
        parts.append(pil_image_to_part(_load_image_for_model(p)))

    try:
        response = client.models.generate_content(
            model=BEHAVIOR_FLOW_MODEL,
            contents=parts,
            config=default_generate_config(system_instruction=system_prompt),
        )
    except Exception as exc:
        logger.error("Gemini behavior-flow clustering failed: %s", exc)
        raise AIProcessingError(f"Behavior flow clustering failed: {exc}") from exc

    content = getattr(response, "text", None) or ""
    if not content:
        raise AIProcessingError("Received empty response from Gemini")

    logger.debug("Behavior flow raw output length: %s", len(content))
    data = _parse_json_array_loose(content)
    if not isinstance(data, list) or not data:
        raise AIProcessingError("Model output must be a non-empty JSON array")

    try:
        items = [BehaviorFlowItem.model_validate(x) for x in data]
    except Exception as exc:
        raise AIProcessingError(f"Invalid behavior flow item shape: {exc}") from exc

    if not items:
        raise AIProcessingError("Model returned no behavior flows")

    expected = set(_expected_ids(len(image_ids)))
    _validate_partition(expected, items)

    return items


class BehaviorFlowClusterService:
    async def organize(
        self,
        input_id: str,
        id_path_pairs: list[tuple[str, str]],
    ) -> BehaviorFlowOrganizeResponse:
        if not id_path_pairs:
            raise AIProcessingError("No images to organize")
        image_ids = [p[0] for p in id_path_pairs]
        image_paths = [p[1] for p in id_path_pairs]

        def _work() -> BehaviorFlowOrganizeResponse:
            flows = _run_gemini_cluster_sync(image_ids, image_paths)
            return BehaviorFlowOrganizeResponse(
                model=BEHAVIOR_FLOW_MODEL,
                input_id=input_id,
                flows=flows,
            )

        try:
            return await asyncio.to_thread(_work)
        except AIProcessingError:
            raise
        except Exception as exc:
            logger.error("Behavior flow cluster service failed: %s", exc)
            raise AIProcessingError(f"Behavior flow cluster service failed: {exc}") from exc


behavior_flow_cluster_service = BehaviorFlowClusterService()
