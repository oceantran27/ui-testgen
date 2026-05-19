"""Tests for scenario writing blueprint derivation."""

from app.model_providers.schemas import BehaviourIntentA5
from app.services.scenario_blueprint_builder_service import build_scenario_blueprints


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
                "visible_elements": [
                    {
                        "element_id": "h1",
                        "element_type": "heading",
                        "role_hint": "informative",
                        "text": ["Heading"],
                    },
                ],
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
    bp = build_scenario_blueprints([intent], _minimal_compressed_catalog())[0]
    assert bp.mandatory_anchors.given
    assert bp.mandatory_anchors.when
    assert bp.mandatory_anchors.then
    assert any("visible_feedback" in a.source for a in bp.mandatory_anchors.then)
    assert not bp.hidden_assertions


def test_blueprint_then_skips_negative_as_mandatory_anchor() -> None:
    catalog = _minimal_compressed_catalog()
    intent = BehaviourIntentA5.model_validate(
        {
            "intent_id": "bi_negintent",
            "source_flow_id": "flow_1",
            "source_flow_name": "Booking",
            "source_flow_type": "single_step_outcome",
            "behaviour_name": "fail",
            "intent_type": "negative",
            "user_intent": "try",
            "business_goal": "x",
            "start_state": "sA",
            "end_state": "sB",
            "trigger_action": {"action_type": "tap", "text": ["Continue"]},
            "expected_result": "blocked",
            "expected_ui_evidence": ["Error shown"],
            "negative_expectations": ["No success confirmation"],
            "confidence": "high",
            "preconditions": [],
            "test_data_requirements": [],
            "user_actions": ["Tap Continue"],
            "warnings": [],
            "assumptions": [],
            "source_transition_ids": [],
        }
    )
    bp = build_scenario_blueprints([intent], catalog)[0]
    assert not any(a.source == "intent.negative_expectations" for a in bp.mandatory_anchors.then)
    assert len(bp.hidden_assertions) == 1
    assert bp.hidden_assertions[0].render_in_gherkin is False


def test_blueprint_when_uses_selected_options_before_trigger() -> None:
    cat = _minimal_compressed_catalog()
    cat["compressed_catalog"][0]["screen_intents"] = [
        {
            "intent_id": "intent_pick",
            "source_group_id": "g1",
            "intent_kind": "selection",
            "intent_name": "pick_slot",
            "local_user_goal": "pick date/time",
            "primary_action": {"action_id": "ac_go", "action_type": "submit", "text": ["Continue"]},
            "secondary_actions": [],
            "selection_options": [
                {
                    "option_ref_type": "element",
                    "option_element_id": "el1",
                    "option_text": ["05/20/2026"],
                    "visible_status": "selected",
                },
                {
                    "option_ref_type": "element",
                    "option_element_id": "el2",
                    "option_text": ["14:00"],
                    "visible_status": "selected",
                },
            ],
            "evidence_refs": [],
        },
    ]
    intent = BehaviourIntentA5.model_validate(
        {
            "intent_id": "bi_whenorder",
            "source_flow_id": "flow_1",
            "source_flow_name": "Booking",
            "source_flow_type": "single_step_outcome",
            "behaviour_name": "pick",
            "intent_type": "positive",
            "user_intent": "go",
            "business_goal": "x",
            "start_state": "sA",
            "end_state": "sB",
            "trigger_action": {"action_type": "tap", "text": ["Continue"]},
            "expected_result": "done",
            "expected_ui_evidence": ["Ok"],
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
    bp = build_scenario_blueprints([intent], cat)[0]
    when = bp.mandatory_anchors.when
    assert when[0].source == "start_state.screen_intents.selection_options"
    assert when[0].text == "05/20/2026"
    assert when[1].text == "14:00"
    assert when[2].source == "intent.trigger_action.text"
