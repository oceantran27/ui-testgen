"""State graph pipeline with external calls mocked."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.state_graph import StateGraphFlowItem, UserIntentEvidenceItem, UserIntentPerImage
from app.schemas.test_scenario_generation import FinalTestOutput
from app.schemas.ui_extraction import (
    NavDestination,
    UIExtractedControl,
    UIExtractionOverview,
    UIExtractionResult,
    UISemanticGroup,
)
from app.services.image_dedup_service import DedupResult
from app.services.state_graph_pipeline_service import state_graph_pipeline_service


def _minimal_ui_extraction() -> UIExtractionResult:
    return UIExtractionResult(
        overview=UIExtractionOverview(viewport_description="Test page"),
        controls=[],
        groups=[],
    )


def _ui_extraction_with_non_primary_background() -> UIExtractionResult:
    return UIExtractionResult(
        overview=UIExtractionOverview(viewport_description="p"),
        controls=[
            UIExtractedControl(
                id="out_scope",
                role="link",
                label="Back",
                value="Back",
                associated_context="",
                is_primary_layer=False,
            ),
            UIExtractedControl(
                id="in_scope",
                role="button",
                label="Go",
                value="Go",
                associated_context="",
                is_primary_layer=True,
            ),
        ],
        groups=[
            UISemanticGroup(
                id="nav",
                summary="nav",
                controls=["out_scope", "in_scope"],
                destinations=[
                    NavDestination(control="out_scope", label="Back"),
                    NavDestination(control="in_scope", label="Go"),
                ],
            ),
        ],
    )


def test_pipeline_run_with_mocks():
    tmp = Path(tempfile.mkdtemp())
    fake_img = tmp / "u.png"
    fake_img.write_bytes(b"fake")  # not valid PNG; we mock extraction anyway

    dedup = DedupResult(
        canonical_paths=[str(fake_img)],
        canonical_image_ids=["abc123def456"],
        input_path_to_image_id={str(fake_img): "abc123def456"},
        dropped_paths=[],
    )
    flows_raw = [
        StateGraphFlowItem(id="flow-1", name="Demo", nodes=["abc123def456"]),
    ]

    with (
        patch(
            "app.services.state_graph_pipeline_service.dedupe_image_paths",
            return_value=dedup,
        ),
        patch(
            "app.services.state_graph_pipeline_service.extract_ui_extraction_gemini_sync",
            return_value=(_minimal_ui_extraction(), 0.1),
        ),
        patch(
            "app.services.state_graph_pipeline_service.generate_user_intents_openai_sync",
            return_value=UserIntentPerImage(
                image_id="abc123def456",
                user_intents=[
                    UserIntentEvidenceItem(intent="Complete checkout", control_ids=["btn_checkout"]),
                ],
            ),
        ),
        patch(
            "app.services.state_graph_pipeline_service.run_state_graph_flow_sync",
            return_value=flows_raw,
        ),
        patch(
            "app.services.state_graph_pipeline_service.generate_all_test_scenarios_async",
            new_callable=AsyncMock,
            return_value=FinalTestOutput(),
        ),
    ):
        result = asyncio.run(
            state_graph_pipeline_service.run(
                input_id="pipe-test",
                saved_paths=[str(fake_img)],
                out_dir=str(tmp / "out"),
            )
        )

    assert result.input_id == "pipe-test"
    assert len(result.flows) == 1
    assert result.flows[0].nodes == ["abc123def456"]
    assert result.final_test_output == FinalTestOutput()


def test_pipeline_passes_scoped_payload_without_is_primary_layer_to_user_intents():
    tmp = Path(tempfile.mkdtemp())
    fake_img = tmp / "u.png"
    fake_img.write_bytes(b"fake")

    dedup = DedupResult(
        canonical_paths=[str(fake_img)],
        canonical_image_ids=["abc123def456"],
        input_path_to_image_id={str(fake_img): "abc123def456"},
        dropped_paths=[],
    )
    flows_raw = [
        StateGraphFlowItem(id="flow-1", name="Demo", nodes=["abc123def456"]),
    ]
    mock_intents = MagicMock(
        return_value=UserIntentPerImage(
            image_id="abc123def456",
            user_intents=[
                UserIntentEvidenceItem(intent="Go somewhere", control_ids=["in_scope"]),
            ],
        )
    )

    with (
        patch(
            "app.services.state_graph_pipeline_service.dedupe_image_paths",
            return_value=dedup,
        ),
        patch(
            "app.services.state_graph_pipeline_service.extract_ui_extraction_gemini_sync",
            return_value=(_ui_extraction_with_non_primary_background(), 0.1),
        ),
        patch(
            "app.services.state_graph_pipeline_service.generate_user_intents_openai_sync",
            mock_intents,
        ),
        patch(
            "app.services.state_graph_pipeline_service.run_state_graph_flow_sync",
            return_value=flows_raw,
        ),
        patch(
            "app.services.state_graph_pipeline_service.generate_all_test_scenarios_async",
            new_callable=AsyncMock,
            return_value=FinalTestOutput(),
        ),
    ):
        asyncio.run(
            state_graph_pipeline_service.run(
                input_id="pipe-test",
                saved_paths=[str(fake_img)],
                out_dir=str(tmp / "out"),
            )
        )

    mock_intents.assert_called_once()
    _image_id, minified_json, _model = mock_intents.call_args[0]
    payload = json.loads(minified_json)
    assert [c["id"] for c in payload["controls"]] == ["in_scope"]
    assert all("is_primary_layer" not in c for c in payload["controls"])
    assert not any(d["control"] == "out_scope" for g in payload["groups"] for d in (g.get("destinations") or []))
