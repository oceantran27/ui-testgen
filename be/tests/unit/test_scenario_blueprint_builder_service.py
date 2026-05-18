"""Tests for scenario writing blueprint derivation."""

from app.model_providers.schemas import BehaviourIntentA5
from app.services.scenario_blueprint_builder_service import build_scenario_blueprints


def _minimal_compressed_catalog() -> dict:
    tax = {
        "domain": "test",
        "screen_type": "listing",
        "presentation_scope": "primary_task",
        "outcome_state_type": "success",
    }
    empty_form = {"has_form": False, "has_visible_values": False, "has_validation_feedback": False}
    vis = {"headings": ["Heading"], "primary_texts": [], "status_texts": []}
    nav = {
        "breadcrumb_texts": [],
        "active_tab_text": None,
        "step_label_text": None,
        "step_index_visible": None,
        "step_total_visible": None,
        "progress_text": None,
    }
    return {
        "compressed_catalog": [
            {
                "state_id": "sA",
                "screen_purpose": "Booking",
                "taxonomy": tax,
                "visible_signature": vis,
                "navigation_cues": nav,
                "state_feedback_summary": [],
                "form_state_summary": empty_form,
                "continuity_entities": [],
                "intent_groups": [],
                "evidence_refs": [],
            },
            {
                "state_id": "sB",
                "screen_purpose": "Done",
                "taxonomy": tax,
                "visible_signature": vis,
                "navigation_cues": nav,
                "state_feedback_summary": [],
                "form_state_summary": empty_form,
                "continuity_entities": [],
                "intent_groups": [],
                "evidence_refs": [],
            },
        ]
    }


def test_blueprint_builder_mandatory_sections() -> None:
    intent = BehaviourIntentA5.model_validate(
        {
            "intent_id": "bi_testintent",
            "source_flow_id": "flow_1",
            "source_flow_name": "Booking",
            "source_flow_type": "single_step_outcome",
            "behaviour_name": "finish",
            "intent_type": "positive",
            "user_intent": "go",
            "business_goal": "x",
            "start_state": "sA",
            "end_state": "sB",
            "trigger_action": {"action_type": "tap", "text": ["Continue"]},
            "expected_result": "done",
            "expected_ui_evidence": ["Success banner"],
            "confidence": "high",
            "preconditions": [],
            "test_data_requirements": [],
            "user_actions": ["Tap Continue"],
            "warnings": [],
            "assumptions": [],
            "negative_expectations": [],
            "source_transition_ids": [],
        }
    )
    bp = build_scenario_blueprints([intent], _minimal_compressed_catalog(), screen_intent_package={})[0]
    assert bp.mandatory_anchors.given
    assert bp.mandatory_anchors.when
    assert bp.mandatory_anchors.then
