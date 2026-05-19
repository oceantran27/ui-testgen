"""Unit tests for deterministic scenario generation (Agent 6) and pre-audit grounding helpers."""

from app.model_providers.schemas import BehaviourIntentA5
from app.services.scenario_evidence_audit_service import (
    _assertion_requires_ui_verbatim_pool_match,
    _merge_audit_pipeline_report_into_payload,
    _pre_audit_grounding,
)
from app.services.scenario_generation_service import _precheck_behaviour_intent_for_scenarios


def _base_behaviour_intent_dict() -> dict:
    """Minimal positive intent that passes deterministic prechecks."""
    return {
        "intent_id": "intent_positive_abcdef012345",
        "source_flow_id": "flow_1",
        "source_flow_name": "Booking",
        "source_flow_type": "single_step_outcome",
        "behaviour_name": "Complete step",
        "intent_type": "positive",
        "user_intent": "confirm",
        "business_goal": "finish flow",
        "start_state": "sA",
        "end_state": "sB",
        "trigger_action": {"action_type": "tap", "text": ["Continue"]},
        "expected_result": "User completes the step.",
        "user_actions": ["Tap Continue"],
        "expected_ui_evidence": ["Success banner"],
        "confidence": "high",
    }


def _minimal_compressed_catalog() -> dict:
    tax = {
        "domain": "test",
        "screen_type": "listing",
        "presentation_scope": "full_screen",
        "outcome_state_type": "success",
    }
    return {
        "compressed_catalog": [
            {
                "state_id": "sA",
                "screen_purpose": "Booking",
                "taxonomy": tax,
                "visible_elements": [],
                "available_actions": [],
                "visible_feedback": [],
                "interaction_groups": [],
                "screen_intents": [],
            },
            {
                "state_id": "sB",
                "screen_purpose": "Done",
                "taxonomy": tax,
                "visible_elements": [],
                "available_actions": [],
                "visible_feedback": [
                    {"feedback_id": "fb_ok", "feedback_type": "success", "text": ["Success banner"]},
                ],
                "interaction_groups": [],
                "screen_intents": [],
            },
        ]
    }


def test_precheck_cross_state_without_user_actions() -> None:
    data = _base_behaviour_intent_dict()
    data["start_state"] = "sA"
    data["end_state"] = "sZ"
    data["user_actions"] = []
    intent = BehaviourIntentA5.model_validate(data)
    issue = _precheck_behaviour_intent_for_scenarios(intent)
    assert issue is not None
    assert issue.item_type == "invalid_intent"


def test_precheck_positive_missing_expected_ui_evidence() -> None:
    data = _base_behaviour_intent_dict()
    data["expected_ui_evidence"] = []
    intent = BehaviourIntentA5.model_validate(data)
    issue = _precheck_behaviour_intent_for_scenarios(intent)
    assert issue is not None
    assert issue.item_type == "insufficient_evidence"


def test_precheck_ordered_sequence_missing_transition_ids() -> None:
    data = _base_behaviour_intent_dict()
    data["source_flow_type"] = "ordered_sequence"
    data["source_transition_ids"] = []
    intent = BehaviourIntentA5.model_validate(data)
    issue = _precheck_behaviour_intent_for_scenarios(intent)
    assert issue is not None
    assert issue.item_type == "insufficient_traceability"


def test_precheck_negative_with_expected_result_passes_without_negative_expectations() -> None:
    data = _base_behaviour_intent_dict()
    data["intent_type"] = "negative"
    data["expected_ui_evidence"] = []
    data["negative_expectations"] = []
    intent = BehaviourIntentA5.model_validate(data)
    issue = _precheck_behaviour_intent_for_scenarios(intent)
    assert issue is None


def test_deterministic_negative_expectations_are_assertions_not_steps() -> None:
    from app.services.scenario_generation_service import build_deterministic_test_scenario_from_intent

    data = _base_behaviour_intent_dict()
    data["intent_type"] = "negative"
    data["expected_ui_evidence"] = ["Error banner"]
    data["negative_expectations"] = ["No success confirmation"]
    intent = BehaviourIntentA5.model_validate(data)
    scn = build_deterministic_test_scenario_from_intent(intent)
    assert not any("not see" in s.text.lower() for s in scn.steps)
    neg_asserts = [a for a in scn.assertions if a.source == "negative_expectation"]
    assert len(neg_asserts) == 1
    assert neg_asserts[0].render_in_gherkin is False
    assert neg_asserts[0].ui_text_grounding_required is False


def test_assertion_ui_pool_eligibility_skips_transition_and_explicit_flag() -> None:
    assert not _assertion_requires_ui_verbatim_pool_match({"assertion_type": "state_transition"})
    assert not _assertion_requires_ui_verbatim_pool_match({"assertion_type": "state_reached"})
    assert not _assertion_requires_ui_verbatim_pool_match(
        {"assertion_type": "ui_evidence_present", "ui_text_grounding_required": False}
    )
    assert _assertion_requires_ui_verbatim_pool_match(
        {"assertion_type": "ui_evidence_present", "expected": "x"}
    )


def test_pre_audit_evidence_counts_ignore_technical_assertion() -> None:
    ui_state_package = {
        "extracted_states": [
            {
                "state_id": "sB",
                "visible_elements": [{"text": ["Success banner"]}],
                "available_actions": [],
                "visible_feedback": [],
            }
        ]
    }
    scenarios = [
        {
            "end_state": "sB",
            "trigger_action": {"text": [], "action_type": "tap"},
            "assertions": [
                {
                    "assertion_type": "state_transition",
                    "expected": "sB",
                    "source": "expected_result",
                    "ui_text_grounding_required": False,
                },
                {"assertion_type": "ui_evidence_present", "expected": "Success banner", "source": "expected_ui_evidence"},
            ],
        }
    ]
    out = _pre_audit_grounding(scenarios, ui_state_package)
    pre = out[0]["pre_audit_results"]
    assert pre["evidence_total_count"] == 1
    assert pre["evidence_found_count"] == 1


def test_pre_audit_includes_keyword_anchor_grounding() -> None:
    scenarios = [
        {
            "end_state": "sB",
            "trigger_action": {"text": [], "action_type": "tap"},
            "assertions": [],
            "pre_generation_grounding": {
                "keyword_anchor_coverage": 0.9,
                "grounding_passed": True,
                "required_anchor_count": 3,
                "matched_anchor_count": 3,
                "missing_anchor_ids": [],
                "wrong_section_anchor_ids": [],
                "unexpected_placeholders": [],
            },
        }
    ]
    out = _pre_audit_grounding(scenarios, {"extracted_states": []})
    assert "keyword_anchor_grounding" in out[0]["pre_audit_results"]


def test_merge_audit_pipeline_report_preserves_existing_error_keys() -> None:
    payload: dict = {"report": {"error": "x", "failed_batch": 2}}
    _merge_audit_pipeline_report_into_payload(payload)
    assert payload["report"]["error"] == "x"
    assert payload["report"]["failed_batch"] == 2
    assert payload["report"]["auto_retry_enabled"] is False
    assert payload["report"]["revision_suggestions_mode"] == "report_only"


def test_run_scenario_generation_with_llm(monkeypatch) -> None:
    from app.services import scenario_generation_service as sgensvc
    import pytest
    from unittest.mock import AsyncMock, MagicMock
    import asyncio
    
    monkeypatch.setattr(sgensvc.settings, "USE_LLM_FOR_SCENARIO_GENERATION", True)
    
    intent_data = _base_behaviour_intent_dict()
    intent_package = {
        "behaviour_intents": [intent_data]
    }
    
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.status.value = "success"
    
    from app.model_providers.schemas import (
        BDDScenarioGenerationResult,
        TestScenarioA6,
        TriggerActionA5,
        TestScenarioStepA6,
        AssertionA6,
        ScenarioGenerationSummaryA6
    )
    
    mock_scenario = TestScenarioA6(
        scenario_id="scn_abc123",
        scenario_name="Confirm step",
        scenario_type="happy_path",
        source_intent_id=intent_data["intent_id"],
        source_flow_id=intent_data["source_flow_id"],
        source_flow_name=intent_data["source_flow_name"],
        source_flow_type=intent_data["source_flow_type"],
        start_state=intent_data["start_state"],
        end_state=intent_data["end_state"],
        trigger_action=TriggerActionA5(action_type="tap", text=["Continue"]),
        test_objective="Verify complete",
        preconditions=[],
        test_data=[],
        steps=[
            TestScenarioStepA6(
                step_number=1, keyword="Given", text="The user is viewing Booking", source="precondition"
            ),
            TestScenarioStepA6(step_number=2, keyword="When", text="Tap Continue", source="user_action"),
            TestScenarioStepA6(
                step_number=3,
                keyword="Then",
                text="User completes the step and sees Success banner.",
                source="expected_result",
            ),
        ],
        expected_results=["User completes the step."],
        assertions=[
            AssertionA6(assertion_type="state_reached", expected="sB", source="expected_result")
        ],
        confidence="high"
    )
    
    mock_response.parsed_output = BDDScenarioGenerationResult(
        test_scenarios=[mock_scenario],
        unresolved_scenario_items=[],
        coverage_matrix=[],
        generation_summary=ScenarioGenerationSummaryA6(
            total_behaviour_intents=1,
            total_test_scenarios=1,
            total_unresolved_scenario_items=0,
            coverage_rate=1.0
        )
    )
    
    call_mock = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(sgensvc.model_adapter, "call_text_structured", call_mock)
    
    out = asyncio.run(
        sgensvc.run_bdd_scenario_generation(
            db,
            "run_12345",
            intent_package,
            compressed_catalog_package=_minimal_compressed_catalog(),
        )
    )
    
    assert out["generation_summary"]["total_test_scenarios"] == 1
    scn = out["test_scenarios"][0]
    assert scn["scenario_name"] == "Confirm step"
    assert scn["scenario_type"] == "happy_path"
    assert len(scn["steps"]) >= 2
    merged = "\n".join(s["text"] for s in scn["steps"])
    assert "Continue" in merged
    assert "Success banner" in merged
    db.commit.assert_awaited()
