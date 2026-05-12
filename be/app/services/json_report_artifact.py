"""Persist structured JSON pipeline reports as Artifact rows + object storage."""
from __future__ import annotations

import json
import uuid
from typing import Any, Mapping, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service


def _artifact_id() -> str:
    return f"art_{uuid.uuid4().hex[:12]}"


async def save_json_report_artifact(
    db: AsyncSession,
    *,
    run_id: str,
    artifact_type: str,
    node_name: str,
    storage_subpath: str,
    payload: Mapping[str, Any] | Any,
    metadata_json: Optional[dict[str, Any]] = None,
) -> Artifact:
    """Upload JSON and insert Artifact. Caller commits the session."""
    body = dict(payload) if isinstance(payload, Mapping) else payload
    report_bytes = json.dumps(body, indent=2, default=str).encode("utf-8")
    report_key = f"artifacts/{run_id}/{storage_subpath}"
    report_uri = storage_service.upload_file(
        report_bytes, report_key, content_type="application/json"
    )
    artifact = Artifact(
        id=_artifact_id(),
        run_id=run_id,
        artifact_type=artifact_type,
        node_name=node_name,
        storage_uri=report_uri,
        metadata_json=metadata_json or {},
    )
    db.add(artifact)
    return artifact
