"""Load scenario validation JSON from the latest matching Artifact for a run."""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.validation_artifacts import SCENARIO_VALIDATION_ARTIFACT_TYPES
from app.db.models.artifact import Artifact
from app.services.storage_service import storage_service


async def load_latest_scenario_validation_payload(
    db: AsyncSession,
    run_id: str,
) -> Optional[dict[str, Any]]:
    """Return parsed JSON from newest artifact (by created_at) among known validation report types."""
    for artifact_type in SCENARIO_VALIDATION_ARTIFACT_TYPES:
        result = await db.execute(
            select(Artifact)
            .where(
                Artifact.run_id == run_id,
                Artifact.artifact_type == artifact_type,
                Artifact.storage_uri.isnot(None),
            )
            .order_by(desc(Artifact.created_at))
            .limit(1)
        )
        art = result.scalar_one_or_none()
        if art and art.storage_uri:
            raw = storage_service.download_file(art.storage_uri)
            return json.loads(raw)
    return None
