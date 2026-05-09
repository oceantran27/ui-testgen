"""
Usage Logger — records model call results to DB and optionally saves raw response as artifact.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_event, logger
from app.db.models.artifact import Artifact
from app.db.models.model_call import ModelCall
from app.model_providers.base import ModelCallStatus, ModelResponse
from app.services.storage_service import storage_service


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


async def log_model_call(
    db: AsyncSession,
    response: ModelResponse,
    job_id: Optional[str] = None,
) -> str:
    """
    Persist a ModelResponse to the model_calls table.
    If ENABLE_MODEL_RAW_RESPONSE_ARTIFACT=true, also saves raw response to object storage.
    Returns the model_call_id.
    """
    call_id = _gen_id("mcall")
    raw_artifact_id: Optional[str] = None

    # 1. Optionally save raw response artifact
    if settings.ENABLE_MODEL_RAW_RESPONSE_ARTIFACT and response.raw_text:
        try:
            artifact_id = _gen_id("art")
            storage_key = f"artifacts/{response.run_id}/model_calls/{response.request_id}/raw_response.json"
            payload = {
                "request_id": response.request_id,
                "task_name": response.task_name,
                "provider": response.provider,
                "model_name": response.model_name,
                "raw_text": response.raw_text,
            }
            storage_service.upload_file(
                json.dumps(payload, indent=2).encode("utf-8"),
                storage_key,
                content_type="application/json",
            )
            artifact = Artifact(
                id=artifact_id,
                run_id=response.run_id,
                artifact_type="model_raw_response",
                node_name=response.node_name,
                storage_uri=f"s3://{settings.STORAGE_BUCKET_NAME}/{storage_key}",
                metadata_json={
                    "request_id": response.request_id,
                    "task_name": response.task_name,
                    "provider": response.provider,
                },
            )
            db.add(artifact)
            raw_artifact_id = artifact_id
        except Exception as e:
            logger.warning(f"Failed to save raw response artifact for {response.request_id}: {e}")

    # 2. Save model_call record
    error_code = None
    error_message = None
    if response.error:
        error_code = str(response.error.error_code)
        error_message = response.error.message[:500] if response.error.message else None

    call = ModelCall(
        id=call_id,
        run_id=response.run_id,
        job_id=job_id,
        node_name=response.node_name,
        task_name=response.task_name,
        provider=response.provider,
        model_name=response.model_name,
        request_type=str(response.request_type),
        status=str(response.status),
        latency_ms=response.latency_ms,
        input_tokens=response.usage.input_tokens if response.usage else None,
        output_tokens=response.usage.output_tokens if response.usage else None,
        total_tokens=response.usage.total_tokens if response.usage else None,
        image_count=response.image_count,
        retry_count=response.retry_count,
        error_code=error_code,
        error_message=error_message,
        raw_output_artifact_id=raw_artifact_id,
    )
    db.add(call)

    try:
        await db.flush()  # flush but don't commit — let caller control transaction
    except Exception as e:
        logger.warning(f"Failed to flush model_call to DB: {e}")

    # 3. Emit log event
    event_name = "model_call_completed" if response.status == ModelCallStatus.SUCCESS else "model_call_failed"
    log_event(
        event_name,
        run_id=response.run_id,
        node_name=response.node_name,
        task_name=response.task_name,
        provider=response.provider,
        model_name=response.model_name,
        latency_ms=response.latency_ms,
        retry_count=response.retry_count,
        status=str(response.status),
        error_code=error_code,
    )

    return call_id
