"""Gemini vision → UI hierarchy JSON (stage 1), shared by pipelines."""

from __future__ import annotations

import logging
import time

from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.ui_hierarchy import UIHierarchyResult
from app.services.gemini_genai_client import default_generate_config, get_gemini_client, pil_image_to_part
from app.services.prompt_service import load_two_stage_ui_hierarchy_prompt
from app.services.ui_hierarchy_payload import parse_ui_hierarchy_payload

logger = logging.getLogger(__name__)


def extract_ui_hierarchy_gemini_sync(image_path: str, gemini_model: str) -> tuple[UIHierarchyResult, float]:
    """
    Run stage-1 UI extraction with Gemini vision.
    Returns (parsed hierarchy, llm_seconds).
    """
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system1 = load_two_stage_ui_hierarchy_prompt()
    client = get_gemini_client()
    try:
        img = Image.open(image_path)
    except Exception as exc:
        logger.error("Failed to open image: %s", exc)
        raise AIProcessingError(f"Failed to read image file: {exc}") from exc

    user1 = (
        "Analyze this UI screenshot and output the UI hierarchy JSON exactly as specified in the system instructions. "
        "Return ONLY the raw JSON."
    )
    t0 = time.perf_counter()
    try:
        response1 = client.models.generate_content(
            model=gemini_model,
            contents=[types.Part.from_text(text=user1), pil_image_to_part(img)],
            config=default_generate_config(system_instruction=system1),
        )
    except Exception as exc:
        logger.error("Gemini UI hierarchy extraction failed: %s", exc)
        raise AIProcessingError(f"UI hierarchy extraction failed: {exc}") from exc
    finally:
        try:
            img.close()
        except Exception:
            pass

    raw1 = response1.text
    if not raw1:
        raise AIProcessingError("Received empty response from Gemini (UI hierarchy)")
    t1 = time.perf_counter()
    return parse_ui_hierarchy_payload(raw1), t1 - t0
