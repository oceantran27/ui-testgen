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
from app.services.gemini_retry import GEMINI_503_RETRY_SLEEP_SEC, is_gemini_503_unavailable
from app.services.prompt_service import load_ui_extraction_prompt
from app.services.ui_extraction_payload import parse_ui_extraction_payload

logger = logging.getLogger(__name__)


def extract_ui_extraction_gemini_sync(image_path: str, gemini_model: str) -> tuple[UIExtractionResult, float]:
    """
    Run stage-1 UI extraction with Gemini vision.
    Returns (parsed extraction, llm_seconds).

    On Google Gemini **503 UNAVAILABLE** (overload), waits 2 seconds and retries indefinitely
    until the call succeeds (other errors still fail fast).
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
        "Analyze this UI screenshot and output ui-flat-v5 JSON: keys schema_version, overview "
        "(viewport_description), controls (flat list with id, role, label, value, associated_context, "
        "is_primary_layer, states), and groups. Return ONLY the raw JSON."
    )
    llm_seconds = 0.0
    response1 = None
    try:
        while True:
            t_attempt = time.perf_counter()
            try:
                response1 = client.models.generate_content(
                    model=gemini_model,
                    contents=[types.Part.from_text(text=user1), pil_image_to_part(img)],
                    config=default_generate_config(system_instruction=system1),
                )
                llm_seconds = time.perf_counter() - t_attempt
                break
            except Exception as exc:
                if is_gemini_503_unavailable(exc):
                    logger.warning(
                        "Gemini UI extraction 503 UNAVAILABLE; sleeping %.1fs then retrying (%s)",
                        GEMINI_503_RETRY_SLEEP_SEC,
                        exc,
                    )
                    time.sleep(GEMINI_503_RETRY_SLEEP_SEC)
                    continue
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
    return parse_ui_extraction_payload(raw1), llm_seconds
