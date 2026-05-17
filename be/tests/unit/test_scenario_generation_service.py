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


def test_precheck_negative_missing_negative_expectations() -> None:
    data = _base_behaviour_intent_dict()
    data["intent_type"] = "negative"
    data["expected_ui_evidence"] = []
    data["negative_expectations"] = []
    intent = BehaviourIntentA5.model_validate(data)
    issue = _precheck_behaviour_intent_for_scenarios(intent)
    assert issue is not None


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


def test_merge_audit_pipeline_report_preserves_existing_error_keys() -> None:
    payload: dict = {"report": {"error": "x", "failed_batch": 2}}
    _merge_audit_pipeline_report_into_payload(payload)
    assert payload["report"]["error"] == "x"
    assert payload["report"]["failed_batch"] == 2
    assert payload["report"]["auto_retry_enabled"] is False
    assert payload["report"]["revision_suggestions_mode"] == "report_only"
