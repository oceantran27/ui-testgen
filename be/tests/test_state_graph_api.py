"""API tests for asynchronous state-graph pipeline."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.v1.endpoints import behavior_flow as behavior_flow_ep
from main import app


@patch.object(behavior_flow_ep, "_run_state_graph_job", new_callable=AsyncMock)
def test_state_graph_post_returns_start_payload(mock_job: AsyncMock) -> None:
    client = TestClient(app)
    files = [("files", ("a.png", b"\x89PNG\r\n\x1a\n", "image/png"))]
    resp = client.post("/api/v1/behavior-flows/state-graph", files=files)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert uuid.UUID(str(data["input_id"]))
    mock_job.assert_awaited_once()


def test_state_graph_sse_emits_completed() -> None:
    class FakePipeline:
        """Minimal stand-in so GET /status does not hit SQLite/LangGraph."""

        def astream(self, *_args, **_kwargs):
            async def _empty():
                if False:
                    yield {}

            return _empty()

        def get_state(self, _thread):
            return SimpleNamespace(values={"error": None})

    rid = str(uuid.uuid4())

    prev = behavior_flow_ep.pipeline_graph
    behavior_flow_ep.pipeline_graph = FakePipeline()
    try:
        with TestClient(app) as client:
            with client.stream("GET", f"/api/v1/behavior-flows/state-graph/status/{rid}") as resp:
                assert resp.status_code == 200
                content_type = resp.headers.get("content-type", "") or ""
                body = resp.read()
        assert content_type.startswith("text/event-stream")
        decoded = decode_last_sse_payload(body)
        assert decoded.get("status") == "completed"
    finally:
        behavior_flow_ep.pipeline_graph = prev


def decode_last_sse_payload(body: bytes) -> dict:
    text = body.decode("utf-8", errors="replace")
    payloads = []
    for line in text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[len("data: ") :]))
    assert payloads
    return payloads[-1]


def test_state_graph_get_status_invalid_uuid() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/behavior-flows/state-graph/status/not-a-uuid")
    assert resp.status_code == 400
