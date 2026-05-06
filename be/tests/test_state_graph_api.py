"""API smoke test for state-graph endpoint with mocked pipeline."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.schemas.state_graph import StateGraphFlowItem, StateGraphOrganizeResponse
from app.schemas.test_scenario_generation import FinalTestOutput
from main import app


@patch("app.api.v1.endpoints.behavior_flow.state_graph_pipeline_service")
def test_state_graph_endpoint_mocked(mock_pipe):
    mock_pipe.run = AsyncMock(
        return_value=StateGraphOrganizeResponse(
            model="gpt-5-mini",
            input_id="test-id",
            flows=[
                StateGraphFlowItem(
                    id="f1",
                    name="Test flow",
                    nodes=["deadbeef"],
                )
            ],
            final_test_output=FinalTestOutput(),
        )
    )

    client = TestClient(app)
    files = [("files", ("a.png", b"\x89PNG\r\n\x1a\n", "image/png"))]
    resp = client.post("/api/v1/behavior-flows/state-graph", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["input_id"] == "test-id"
    assert len(data["flows"]) == 1
    assert data["flows"][0]["nodes"] == ["deadbeef"]
    assert data["final_test_output"]["isolated_scenarios"] == []
    assert data["final_test_output"]["flow_scenarios"] == []
