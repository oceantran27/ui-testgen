"""Unit tests for Scenario Evidence Audit (Agent 7) helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.model_providers.schemas import (
    FinalOutputSummaryA7,
    HallucinationFlagsA7,
    ScenarioAcceptanceDecisionA7,
    ScenarioValidationResult,
    ValidationScoresA7,
    ValidatedScenarioA7,
)
from app.services.scenario_evidence_audit_service import (
    _batch_integrity_message,
    _batch_semantics_message,
    _enforce_acceptance_and_reliability,
    _pre_audit_grounding,
    normalize_ui_text,
)


def test_normalize_ui_text_nfkc_whitespace_case() -> None:
    assert normalize_ui_text("  Hello,\u00a0World!! ") == "hello , world!!"


def test_normalize_ui_text_empty() -> None:
    assert normalize_ui_text("") == ""


def test_pre_audit_trigger_scope_source_state() -> None:
    ui_state_package = {
        "extracted_states": [
            {
                "state_id": "sA",
                "visible_elements": [{"text": ["Tap Continue"]}],
                "available_actions": [],
                "visible_feedback": [],
            },
            {
                "state_id": "sB",
                "visible_elements": [{"text": ["Other"]}],
                "available_actions": [],
                "visible_feedback": [],
            },
        ]
    }
    fd = {
        "report": {"candidate_edges": [{"edge_id": "e1", "from_state": "sA", "to_state": "sB"}]},
        "candidate_flows": [{"flow_id": "flow_1", "transition_edge_ids": ["e1"]}],
    }
    scenarios = [
        {
            "start_state": "sA",
            "source_flow_id": "flow_1",
            "source_transition_indexes": [0],
            "end_state": "sB",
            "trigger_action": {"text": ["Tap Continue"], "action_type": "tap"},
            "assertions": [],
        }
    ]
    out = _pre_audit_grounding(scenarios, ui_state_package, fd)
    pre = out[0]["pre_audit_results"]
    assert pre["trigger_action_found"] is True
    assert pre["trigger_action_grounding_scope"] == "source_state"
    assert pre["trigger_action_found_in_source_state"] is True


def test_pre_audit_trigger_scope_transition_path_not_on_start() -> None:
    ui_state_package = {
        "extracted_states": [
            {
                "state_id": "sA",
                "visible_elements": [{"text": ["Wrong label"]}],
                "available_actions": [],
                "visible_feedback": [],
            },
            {
                "state_id": "sB",
                "visible_elements": [{"text": ["Tap Continue"]}],
                "available_actions": [],
                "visible_feedback": [],
            },
        ]
    }
    fd = {
        "report": {"candidate_edges": [{"edge_id": "e1", "from_state": "sA", "to_state": "sB"}]},
        "candidate_flows": [{"flow_id": "flow_1", "transition_edge_ids": ["e1"]}],
    }
    scenarios = [
        {
            "start_state": "sA",
            "source_flow_id": "flow_1",
            "source_transition_indexes": [0],
            "end_state": "sB",
            "trigger_action": {"text": ["Tap Continue"], "action_type": "tap"},
            "assertions": [],
        }
    ]
    out = _pre_audit_grounding(scenarios, ui_state_package, fd)
    pre = out[0]["pre_audit_results"]
    assert pre["trigger_action_found"] is True
    assert pre["trigger_action_grounding_scope"] == "transition_path"
    assert pre["trigger_action_found_in_source_state"] is False


def test_pre_audit_value_literal_from_user_action_step() -> None:
    ui_state_package = {
        "extracted_states": [
            {
                "state_id": "sA",
                "visible_elements": [{"text": ["Continue"]}],
                "available_actions": [],
                "visible_feedback": [],
            }
        ]
    }
    scenarios = [
        {
            "start_state": "sA",
            "source_flow_id": "flow_x",
            "end_state": "sA",
            "trigger_action": {"text": ["Continue"], "action_type": "tap"},
            "steps": [
                {"step_number": 1, "keyword": "When", "text": 'Select time "09:00"', "source": "user_action"}
            ],
            "assertions": [
                {"assertion_type": "ui_evidence_present", "expected": "Shows 09:00", "source": "expected_ui_evidence"}
            ],
        }
    ]
    out = _pre_audit_grounding(scenarios, ui_state_package, None)
    pre = out[0]["pre_audit_results"]
    assert pre["trigger_action_found"] is True


def test_pre_audit_value_literal_missing_from_corpus_fails_trigger() -> None:
    ui_state_package = {
        "extracted_states": [
            {
                "state_id": "sA",
                "visible_elements": [{"text": ["Continue"]}],
                "available_actions": [],
                "visible_feedback": [],
            }
        ]
    }
    scenarios = [
        {
            "start_state": "sA",
            "source_flow_id": "flow_x",
            "end_state": "sA",
            "trigger_action": {"text": ["Continue"], "action_type": "tap"},
            "steps": [],
            "assertions": [
                {"assertion_type": "ui_evidence_present", "expected": "Shows 09:00", "source": "expected_ui_evidence"}
            ],
        }
    ]
    out = _pre_audit_grounding(scenarios, ui_state_package, None)
    pre = out[0]["pre_audit_results"]
    assert pre["trigger_action_found"] is False
    assert pre["trigger_action_grounding_scope"] == "none"


def test_batch_integrity_detects_missing_id() -> None:
    chunk = [{"scenario_id": "a"}, {"scenario_id": "b"}]
    batch = ScenarioValidationResult(
        validated_scenarios=[
            ValidatedScenarioA7(
                scenario_id="a",
                source_flow_id="f",
                source_intent_id="i",
                scenario_name="n",
                scenario_type="happy_path",
                validation_status="validated",
                final_reliability=0.9,
                scores=ValidationScoresA7(),
                step_audits=[],
                hallucination_flags=HallucinationFlagsA7(),
                revision_suggestions=[],
                acceptance_decision=ScenarioAcceptanceDecisionA7(
                    include_in_final_output=True, reason="ok"
                ),
            )
        ],
        final_output_summary=FinalOutputSummaryA7(),
        package_warnings=[],
    )
    msg = _batch_integrity_message(chunk, batch)
    assert msg is not None
    assert "missing" in msg


def test_batch_semantics_invalid_include() -> None:
    batch = ScenarioValidationResult(
        validated_scenarios=[
            ValidatedScenarioA7(
                scenario_id="a",
                source_flow_id="f",
                source_intent_id="i",
                scenario_name="n",
                scenario_type="happy_path",
                validation_status="rejected",
                final_reliability=0.2,
                scores=ValidationScoresA7(),
                step_audits=[],
                hallucination_flags=HallucinationFlagsA7(),
                revision_suggestions=[],
                acceptance_decision=ScenarioAcceptanceDecisionA7(
                    include_in_final_output=True, reason="wrong"
                ),
            )
        ],
        final_output_summary=FinalOutputSummaryA7(),
        package_warnings=[],
    )
    assert _batch_semantics_message(batch) is not None


def test_enforce_acceptance_needs_revision_forces_exclude() -> None:
    v = ValidatedScenarioA7(
        scenario_id="a",
        source_flow_id="f",
        source_intent_id="i",
        scenario_name="n",
        scenario_type="happy_path",
        validation_status="needs_revision",
        final_reliability=0.8,
        scores=ValidationScoresA7(),
        step_audits=[],
        hallucination_flags=HallucinationFlagsA7(),
        revision_suggestions=[],
        acceptance_decision=ScenarioAcceptanceDecisionA7(include_in_final_output=True, reason="llm"),
    )
    out, downgrade = _enforce_acceptance_and_reliability([v])
    assert downgrade is False
    assert out[0].acceptance_decision.include_in_final_output is False


def test_enforce_reliability_downgrade_validated_to_low_confidence() -> None:
    v = ValidatedScenarioA7(
        scenario_id="a",
        source_flow_id="f",
        source_intent_id="i",
        scenario_name="n",
        scenario_type="happy_path",
        validation_status="validated",
        final_reliability=0.65,
        scores=ValidationScoresA7(),
        step_audits=[],
        hallucination_flags=HallucinationFlagsA7(),
        revision_suggestions=[],
        acceptance_decision=ScenarioAcceptanceDecisionA7(include_in_final_output=True, reason="ok"),
    )
    out, downgrade = _enforce_acceptance_and_reliability([v])
    assert downgrade is True
    assert out[0].validation_status == "low_confidence"


def test_run_audit_fallback_on_batch_integrity() -> None:
    import asyncio

    from app.core.config import settings
    from app.services.scenario_evidence_audit_service import run_scenario_evidence_audit

    primary = ValidatedScenarioA7(
        scenario_id="wrong",
        source_flow_id="f",
        source_intent_id="i",
        scenario_name="n",
        scenario_type="happy_path",
        validation_status="validated",
        final_reliability=0.9,
        scores=ValidationScoresA7(),
        step_audits=[],
        hallucination_flags=HallucinationFlagsA7(),
        revision_suggestions=[],
        acceptance_decision=ScenarioAcceptanceDecisionA7(include_in_final_output=True, reason="ok"),
    )
    fixed = ValidatedScenarioA7(
        scenario_id="scenario_1",
        source_flow_id="f",
        source_intent_id="i",
        scenario_name="n",
        scenario_type="happy_path",
        validation_status="validated",
        final_reliability=0.9,
        scores=ValidationScoresA7(),
        step_audits=[],
        hallucination_flags=HallucinationFlagsA7(),
        revision_suggestions=[],
        acceptance_decision=ScenarioAcceptanceDecisionA7(include_in_final_output=True, reason="ok"),
    )

    call_models: list[str] = []

    class Resp:
        def __init__(self, parsed):
            self.status = type("S", (), {"value": "success"})
            self.parsed_output = parsed
            self.error = None

    async def fake_call(**kwargs):
        call_models.append(kwargs.get("model_name_override") or "")
        name = kwargs.get("model_name_override")
        if name == settings.SCENARIO_VALIDATION_MODEL_NAME:
            return Resp(
                ScenarioValidationResult(
                    validated_scenarios=[primary],
                    final_output_summary=FinalOutputSummaryA7(),
                    package_warnings=[],
                )
            )
        return Resp(
            ScenarioValidationResult(
                validated_scenarios=[fixed],
                final_output_summary=FinalOutputSummaryA7(),
                package_warnings=[],
            )
        )

    pkg = {"test_scenarios": [{"scenario_id": "scenario_1", "trigger_action": {"text": []}, "assertions": []}]}

    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock(return_value=exec_result)

    result_holder: list = []

    async def _inner() -> None:
        with patch("app.services.scenario_evidence_audit_service.model_adapter.call_text_structured", fake_call):
            with patch("app.services.scenario_evidence_audit_service.save_json_report_artifact", AsyncMock()):
                with patch(
                    "app.services.scenario_evidence_audit_service.prompt_manager.get_prompt",
                    return_value="sys",
                ):
                    result_holder.append(
                        await run_scenario_evidence_audit(
                            mock_db,
                            run_id="run_test",
                            scenario_draft_package=pkg,
                            ui_state_package=None,
                            flow_discovery_result=None,
                            intent_package=None,
                            screen_intent_package=None,
                        )
                    )

    asyncio.run(_inner())

    assert settings.SCENARIO_VALIDATION_FALLBACK_MODEL_NAME != settings.SCENARIO_VALIDATION_MODEL_NAME
    assert len(call_models) >= 2
    assert result_holder[0]["validated_scenarios"][0]["scenario_id"] == "scenario_1"

