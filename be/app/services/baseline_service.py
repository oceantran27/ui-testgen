"""
Baseline Service — Phase Research v1.
Runs a single-agent LLM call for direct UI-to-Gherkin comparison.
"""
import json
import time
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.core.prompt_manager import prompt_manager
from app.db.models.image import Image
from app.model_providers import model_adapter
from app.model_providers.base import ImageInput
from app.model_providers.schemas import BaselineGenerationResult
from app.services.json_report_artifact import save_json_report_artifact

async def run_baseline_generation(
    db: AsyncSession,
    run_id: str,
    image_ids: List[str],
) -> Dict[str, Any]:
    """
    Single-agent baseline: Screenshots → Gherkin in one LLM call.
    """
    start_time = time.time()
    log_event("baseline_generation_started", run_id=run_id)

    if not image_ids:
        return {"error": "NO_IMAGE_IDS"}

    # 1. Load images from DB
    result = await db.execute(
        select(Image).where(Image.id.in_(image_ids), Image.run_id == run_id)
    )
    images = result.scalars().all()
    
    image_inputs = [
        ImageInput(image_id=img.id, storage_uri=img.storage_uri)
        for img in images if img.storage_uri
    ]

    if not image_inputs:
        return {"error": "NO_VALID_IMAGES"}

    # 2. Call vision LLM
    system_instruction = prompt_manager.get_prompt("baseline_single_agent")
    user_instruction = "Analyze these screenshots and generate BDD scenarios directly in the requested JSON format."

    response = await model_adapter.call_vision_structured(
        task_name="baseline_generation",
        run_id=run_id,
        node_name="baseline_node",
        system_instruction=system_instruction,
        user_instruction=user_instruction,
        image_inputs=image_inputs,
        output_schema=BaselineGenerationResult,
        prompt_name="baseline_single_agent_prompt",
        prompt_version="v1",
        provider_override=settings.BASELINE_MODEL_PROVIDER,
        model_name_override=settings.BASELINE_MODEL_NAME,
    )

    if response.status.value != "success" or not response.parsed_output:
        logger.error(f"Baseline Generation failed: {response.error}")
        return {"error": str(response.error)}

    result_data: BaselineGenerationResult = response.parsed_output
    payload = result_data.model_dump()

    # 3. Save as artifact
    await save_json_report_artifact(
        db,
        run_id=run_id,
        artifact_type="baseline_comparison_report",
        node_name="baseline_node",
        storage_subpath="research/baseline_report.json",
        payload=payload
    )
    await db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    log_event("baseline_generation_completed", run_id=run_id, duration_ms=duration_ms)

    return payload
