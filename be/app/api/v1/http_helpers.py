"""Shared helpers for logging JSON lines and correlation headers."""

import json
import uuid
from typing import Any, Optional


def json_compact(payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        return json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def sanitize_optional_id(raw: Optional[str], *, max_len: int = 128) -> Optional[str]:
    if raw is None:
        return None
    normalized = str(raw).strip()
    if not normalized:
        return None
    if len(normalized) > max_len:
        return normalized[:max_len]
    return normalized


def ensure_correlation_ids(
    request_id: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> tuple[str, str]:
    return (
        sanitize_optional_id(request_id) or str(uuid.uuid4()),
        sanitize_optional_id(batch_id) or str(uuid.uuid4()),
    )


def correlation_response_headers(request_id: str, batch_id: str) -> dict[str, str]:
    return {
        "X-Request-Id": request_id,
        "X-Batch-Id": batch_id,
        "Access-Control-Expose-Headers": "X-Request-Id,X-Batch-Id",
    }
