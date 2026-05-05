"""OpenAI text → user intents JSON for one screen (UI hierarchy evidence)."""

from __future__ import annotations

import logging

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import AIProcessingError
from app.schemas.state_graph import UserIntentPerImage
from app.services.prompt_service import load_user_intents_generation_prompt

logger = logging.getLogger(__name__)


def generate_user_intents_openai_sync(
    image_id: str,
    hierarchy_minified_json: str,
    openai_model: str,
) -> UserIntentPerImage:
    if not settings.OPENAI_API_KEY:
        raise AIProcessingError("OPENAI_API_KEY is not configured")

    system_prompt = load_user_intents_generation_prompt()
    user_text = (
        f"The canonical image_id for this screen is: {image_id}\n\n"
        "UI hierarchy JSON (sole source of truth for visible UI wording):\n"
        f"{hierarchy_minified_json}\n\n"
        "Return exactly one JSON object with keys image_id and user_intents per system instructions. "
        "The image_id in your output MUST match the provided image_id exactly."
    )

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
        logger.error("OpenAI user-intent generation failed: %s", exc)
        raise AIProcessingError(f"User intent generation failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise AIProcessingError("Received empty response from OpenAI (user intents)")

    try:
        parsed = UserIntentPerImage.model_validate_json(content)
    except Exception as exc:
        raise AIProcessingError(f"Invalid user intents payload: {exc}") from exc

    if parsed.image_id != image_id:
        logger.warning(
            "Model returned mismatched image_id %r (expected %r); coercing.",
            parsed.image_id,
            image_id,
        )
        parsed = UserIntentPerImage(image_id=image_id, user_intents=parsed.user_intents)

    return parsed
