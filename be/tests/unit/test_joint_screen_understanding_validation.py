"""Structural validation tests for joint understanding output."""

from app.services.joint_screen_understanding_validation import validate_joint_screen_understanding_structured


def test_validator_detects_bad_intent_action_ref():
    state_row = {
        "visible_elements": [{"element_id": "st_x_el_1"}],
        "available_actions": [{"action_id": "st_x_ac_1"}],
        "visible_feedback": [],
        "interaction_groups": [
            {
                "group_id": "st_x_ig_1",
                "element_ids": ["st_x_el_1"],
                "action_ids": ["st_x_ac_1"],
                "feedback_ids": [],
            }
        ],
    }
    intent_payload = {
        "screen_behaviour_intents": [
            {
                "source_group_id": "st_x_ig_1",
                "primary_action_id": "st_x_ac_nope",
                "commit_action_id": None,
                "secondary_action_ids": [],
                "required_input_element_ids": [],
                "evidence_refs": [],
                "selection_options": [],
                "local_action_sequence_templates": [],
            }
        ],
        "unresolved_screen_groups": [],
    }
    rep = validate_joint_screen_understanding_structured(state_row, intent_payload)
    assert rep.invalid_intent_primary_action_refs >= 1


def test_validator_passes_aligned_intent():
    state_row = {
        "visible_elements": [{"element_id": "st_x_el_1"}],
        "available_actions": [{"action_id": "st_x_ac_1"}],
        "visible_feedback": [],
        "interaction_groups": [
            {
                "group_id": "st_x_ig_1",
                "element_ids": ["st_x_el_1"],
                "action_ids": ["st_x_ac_1"],
                "feedback_ids": [],
            }
        ],
    }
    intent_payload = {
        "screen_behaviour_intents": [
            {
                "source_group_id": "st_x_ig_1",
                "primary_action_id": "st_x_ac_1",
                "commit_action_id": "st_x_ac_1",
                "secondary_action_ids": [],
                "required_input_element_ids": ["st_x_el_1"],
                "evidence_refs": [
                    {"evidence_type": "action_text", "source_id": "st_x_ac_1"},
                ],
                "selection_options": [],
                "local_action_sequence_templates": [],
            }
        ],
        "unresolved_screen_groups": [],
    }
    rep = validate_joint_screen_understanding_structured(state_row, intent_payload)
    assert rep.invalid_intent_primary_action_refs == 0
    assert rep.invalid_intent_required_input_refs == 0
    assert rep.invalid_intent_evidence_refs == 0
