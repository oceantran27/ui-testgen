"""OpenAI text → user intents JSON for one screen (ui-flat-v5 extraction)."""

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
    """
    Call OpenAI with the user-intents system prompt and a minified ui-flat-v5 extraction
    (flat ``controls`` + ``groups``), typically after primary-layer filtering for the pipeline.
    """
    if not settings.OPENAI_API_KEY:
        raise AIProcessingError("OPENAI_API_KEY is not configured")

    system_prompt = load_user_intents_generation_prompt()
    user_text = (
        f"The canonical image_id for this screen is: {image_id}\n"
        "In this API flow an image_id is always provided above. Your root JSON object MUST use "
        "exactly that value for the image_id field (character-for-character). Do not use "
        '"not_provided" for image_id here.\n\n'
        "UI extraction JSON (schema ui-flat-v5; sole source of truth for visible UI wording, "
        "including overview.viewport_description, controls' value/label/states, and groups "
        "attachments such as primary_actions, search, filters, sorts, pagination, destinations, "
        "content):\n"
        f"{hierarchy_minified_json}\n\n"
        "Payload note: controls in this JSON were already filtered to the primary interactive "
        "layer (equivalent to is_primary_layer true upstream). The is_primary_layer field is "
        "omitted from control objects for brevity; do not assume dimmed background controls are "
        "present.\n\n"
        "Return exactly one raw JSON object per the system instructions: only top-level keys "
        "image_id and user_intents; each user_intents element only intent (string) and control_ids "
        "(non-empty string array). No extra keys."
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
