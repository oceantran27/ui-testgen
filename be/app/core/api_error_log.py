"""Plain-console + optional JSON file for HTTP 4xx/5xx from the API (frontend → backend)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from starlette.requests import Request

from app.core.config import settings


def _be_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _redacted_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in ("authorization", "cookie"):
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def _parse_response_payload(body: Optional[bytes]) -> Any:
    if not body:
        return None
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return None
    if len(text) > 16_000:
        return text[:16_000] + "...(truncated)"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def api_error_logging_middleware(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)

    if response.status_code < 400 or not settings.API_ERROR_LOG_ENABLED:
        return response

    rid = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    err_code = None
    message = None
    resp_obj: Any = None
    body = getattr(response, "body", None)
    if isinstance(body, memoryview):
        body = body.tobytes()
    if isinstance(body, bytes):
        resp_obj = _parse_response_payload(body)
        if isinstance(resp_obj, Mapping):
            err_code = resp_obj.get("error_code")
            message = resp_obj.get("message")

    print("-----", flush=True)
    print(
        f"ERROR API {request.method} {request.url.path} status={response.status_code}",
        flush=True,
    )
    if err_code is not None:
        print(f"error_code={err_code}", flush=True)
    if message is not None:
        print(f"message={message}", flush=True)
    print(f"request_id={rid}", flush=True)
    print("-----", flush=True)

    root = _be_root() / settings.API_ERROR_LOG_ROOT
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump_path = root / f"{ts}_{rid}.json"
    payload = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "request_id": rid,
        "method": request.method,
        "path": request.url.path,
        "query": str(request.url.query) if request.url.query else "",
        "status_code": response.status_code,
        "client_host": getattr(request.client, "host", None),
        "headers": _redacted_headers(request),
        "response": resp_obj,
    }
    try:
        dump_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError:
        pass

    return response
