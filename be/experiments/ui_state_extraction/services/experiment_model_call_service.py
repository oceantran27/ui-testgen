"""Call production vision stack for joint screen understanding (experiment harness)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.config import settings
from app.core.prompt_manager import prompt_manager
from app.model_providers import model_adapter
from app.model_providers.base import ImageInput, ModelResponse
from app.model_providers.schemas import JointScreenUnderstandingResult
from app.services.screen_intent_prompt_render import render_phase2_taxonomy_system_suffix

from experiments.ui_state_extraction import config


def _build_system_instruction() -> str:
    base = prompt_manager.get_prompt(config.PROMPT_NAME).strip()
    if config.MATCH_JOINT_SERVICE_SYSTEM_PROMPT:
        return f"{base}\n\n{render_phase2_taxonomy_system_suffix()}"
    return base


def _build_user_instruction(image_id: str, image_uri: str) -> str:
    meta = {"image_id": image_id, "image_uri": image_uri}
    return (
        "Analyze this screenshot. Return JSON matching JointScreenUnderstandingResult: "
        'top-level keys "ui_state" and "screen_intents". '
        "Use metadata image_id exactly.\n"
        f"Metadata JSON: {json.dumps(meta, ensure_ascii=False)}"
    )


async def call_joint_screen_understanding_for_experiment(
    *,
    run_id: str,
    image_id: str,
    image_uri: str,
    image_input: ImageInput,
) -> ModelResponse:
    system_instruction = _build_system_instruction()
    user_instruction = _build_user_instruction(image_id, image_uri)
    return await model_adapter.call_vision_structured(
        task_name="joint_screen_understanding",
        run_id=run_id,
        node_name="ui_state_extraction_module1",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        image_inputs=[image_input],
        output_schema=JointScreenUnderstandingResult,
        prompt_name=config.PROMPT_NAME,
        prompt_version="v1",
        provider_override=settings.JOINT_SCREEN_UNDERSTANDING_PROVIDER,
        model_name_override=settings.JOINT_SCREEN_UNDERSTANDING_MODEL_NAME,
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
