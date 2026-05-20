"""Unit tests for raw_capture runner (mocked LLM; no DB)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.model_providers.base import ModelCallStatus
from app.model_providers.schemas import (
    FlowDiscoveryCandidateFlow,
    FlowDiscoveryStep,
    FlowDiscoveryTriggerAction,
    GlobalFlowDiscoveryResult,
)

from experiments.flow_discovery.raw_capture.raw_flow_discovery_runner import ExperimentRawFlowDiscoveryRunner


def _screen(state_id: str, outcome: str = "neutral") -> dict:
    return {
        "state_id": state_id,
        "screen_purpose": "login",
        "taxonomy": {
            "domain": "authentication",
            "screen_type": "auth",
            "presentation_scope": "full_screen",
            "outcome_state_type": outcome,
        },
        "visible_elements": [],
        "available_actions": [
            {"action_id": "ac_go", "action_type": "submit", "text": ["Go"], "action_priority": "primary"},
        ],
        "visible_feedback": [],
        "interaction_groups": [],
        "screen_intents": [
            {
                "intent_id": "intent_login",
                "source_group_id": "g1",
                "intent_kind": "submission",
                "intent_name": "submit",
                "local_user_goal": "login",
                "primary_action": {"action_id": "ac_go", "action_type": "submit", "text": ["Go"]},
                "secondary_actions": [],
                "evidence_refs": [],
            }
        ],
    }


def _pkg(*states: dict) -> dict:
    return {
        "catalog_version": "compressed_catalog_v3",
        "catalog_purpose": "global_flow_discovery_input",
        "compressed_catalog": list(states),
    }


def test_raw_capture_writes_envelope_single_file(tmp_path: Path) -> None:
    cat_path = tmp_path / "compressed_catalog_package.json"
    compressed = _pkg(_screen("s_a"))
    cat_path.write_text(json.dumps(compressed), encoding="utf-8")

    parsed_out = GlobalFlowDiscoveryResult(
        candidate_flows=[
            FlowDiscoveryCandidateFlow(
                flow_id="fx",
                flow_name="demo",
                flow_type="single_step_outcome",
                ordered_steps=[
                    FlowDiscoveryStep(
                        state_id="s_a",
                        step_role="entry",
                        next_trigger_action=FlowDiscoveryTriggerAction(
                            action_id="ac_go",
                            action_type="submit",
                            text=["Go"],
                            intent_id="intent_login",
                        ),
                    ),
                ],
            ),
        ]
    )

    async def fake_caller(**_kwargs):  # pragma: no cover - thin stub
        class R:
            status = ModelCallStatus.SUCCESS
            parsed_output = parsed_out
            provider = "stub"
            model_name = "stub"
            latency_ms = 2
            error = None

        return R()

    async def run() -> None:
        out_path = tmp_path / "raw_model_output.json"
        runner = ExperimentRawFlowDiscoveryRunner(model_caller=fake_caller, validate_screen_count=False)
        await runner.run_from_compressed_catalog(
            "demoauth",
            cat_path,
            run_id="unit_run",
            write_to_path=out_path,
        )
        body = json.loads(out_path.read_text(encoding="utf-8"))
        assert "raw_model_output" in body
        assert body["repaired_model_output"]
        assert isinstance(body["validation_metrics"], dict)
        assert body["validation_metrics"]
        assert "pre_scan" in body["validation_metrics"]

    asyncio.run(run())


def test_raw_capture_llm_failure_still_writes_envelope(tmp_path: Path) -> None:
    cat_path = tmp_path / "catalog.json"
    cat_path.write_text(json.dumps(_pkg(_screen("s_a"))), encoding="utf-8")

    async def fail(**_kw):
        class E:
            message = "unit_fail_llm"

        class R:
            status = ModelCallStatus.FAILED
            parsed_output = None
            provider = "stub"
            model_name = "stub"
            latency_ms = 3
            error = E()

        return R()

    async def run() -> None:
        out_path = tmp_path / "failed.json"
        runner = ExperimentRawFlowDiscoveryRunner(model_caller=fail, validate_screen_count=False)
        await runner.run_from_compressed_catalog(
            "demoauth",
            cat_path,
            write_to_path=out_path,
        )
        blob = json.loads(out_path.read_text(encoding="utf-8"))
        assert blob["repaired_model_output"] is None
        assert blob["discovery_warnings"][0].startswith("LLM_FAILED:")
        assert blob["validation_metrics"].get("failure") is True

    asyncio.run(run())
