"""Gemini vision → UI extraction JSON (stage 1), shared by pipelines."""

from __future__ import annotations

import logging
import time

from google.genai import types
from PIL import Image

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.ui_extraction import UIExtractionResult
from app.services.gemini_genai_client import default_generate_config, get_gemini_client, pil_image_to_part
from app.services.prompt_service import load_ui_extraction_prompt
from app.services.ui_extraction_payload import parse_ui_extraction_payload

logger = logging.getLogger(__name__)


def extract_ui_extraction_gemini_sync(image_path: str, gemini_model: str) -> tuple[UIExtractionResult, float]:
    """
    Run stage-1 UI extraction with Gemini vision.
    Returns (parsed extraction, llm_seconds).
    """
    if not settings.GEMINI_API_KEY:
        raise AIProcessingError("GEMINI_API_KEY is not configured")
    system1 = load_ui_extraction_prompt()
    client = get_gemini_client()
    try:
        img = Image.open(image_path)
    except Exception as exc:
        logger.error("Failed to open image: %s", exc)
        raise AIProcessingError(f"Failed to read image file: {exc}") from exc

    user1 = (
        "Analyze this UI screenshot and output the flat controls + semantic groups JSON exactly as specified "
        "in the system instructions. Return ONLY the raw JSON."
    )
    t0 = time.perf_counter()
    try:
        response1 = client.models.generate_content(
            model=gemini_model,
            contents=[types.Part.from_text(text=user1), pil_image_to_part(img)],
            config=default_generate_config(system_instruction=system1),
        )
    except Exception as exc:
        logger.error("Gemini UI extraction failed: %s", exc)
        raise AIProcessingError(f"UI extraction failed: {exc}") from exc
    finally:
        try:
            img.close()
        except Exception:
            pass

    raw1 = response1.text
    if not raw1:
        raise AIProcessingError("Received empty response from Gemini (UI extraction)")
    t1 = time.perf_counter()
    return parse_ui_extraction_payload(raw1), t1 - t0
