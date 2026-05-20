"""Pydantic round-trip for JointScreenUnderstandingResult enums (taxonomy drift guard)."""

from app.model_providers.schemas import JointScreenUnderstandingResult


def test_joint_roundtrip_coerces_legacy_outcome_domain_and_accept_new_enums():
    raw = {
        "ui_state": {
            "state_id": "state_x",
            "screen_purpose": "demo",
            "presentation_scope": "full_screen",
            "screen_type": "wizard_step",
            "outcome_state_type": "confirmation_required",
            "domain": "not_in_vocab",
            "visible_elements": [
                {
                    "element_id": "el_001",
                    "element_type": "file_input",
                    "text": ["Avatar"],
                    "role_hint": "status_indicator",
                    "visual_region": "main",
                }
            ],
            "available_actions": [
                {
                    "action_id": "ac_001",
                    "action_type": "click",
                    "text": ["Go"],
                    "action_priority": "destructive",
                    "visual_region": "main",
                }
            ],
            "visible_feedback": [],
            "interaction_groups": [
                {
                    "group_id": "ig_001",
                    "group_type": "tabs",
                    "element_ids": ["el_001"],
                    "action_ids": ["ac_001"],
                    "feedback_ids": [],
                    "primary_action_id": "ac_001",
                    "group_evidence": [
                        {"evidence_type": "explicit_container", "description": "x"}
                    ],
                    "group_confidence": "high",
                }
            ],
        },
        "screen_intents": {
            "screen_behaviour_intents": [
                {
                    "source_group_id": "ig_001",
                    "intent_kind": "creation",
                    "intent_name": "create",
                    "local_user_goal": "start",
                    "primary_action_id": "ac_001",
                    "commit_action_id": "ac_001",
                    "secondary_action_ids": [],
                    "selection_options": [],
                    "local_action_sequence_templates": [
                        {
                            "sequence_name": "s1",
                            "steps": [
                                {
                                    "step_type": "open",
                                    "source_action_id": "ac_001",
                                    "source_element_id": "el_001",
                                }
                            ],
                            "outcome_prediction_allowed": False,
                        }
                    ],
                    "required_input_element_ids": [],
                    "evidence_refs": [
                        {"evidence_type": "non_text_label", "source_id": "el_001"}
                    ],
                    "model_confidence": "high",
                }
            ],
            "unresolved_screen_groups": [],
        },
    }
    m = JointScreenUnderstandingResult.model_validate(raw)
    assert m.ui_state.screen_type == "form"
    assert m.ui_state.outcome_state_type == "neutral"
    assert m.ui_state.domain == "unknown"
    assert m.ui_state.visible_elements[0].role_hint == "status"
    assert m.ui_state.visible_elements[0].element_type == "file_input"
    assert m.screen_intents.screen_behaviour_intents[0].intent_kind == "creation"
    st = m.screen_intents.screen_behaviour_intents[0].local_action_sequence_templates[
        0
    ].steps[0].step_type
    assert st == "open_container"
    ev = m.screen_intents.screen_behaviour_intents[0].evidence_refs[0].evidence_type
    assert ev == "control_label"


def test_joint_roundtrip_normalizes_legacy_action_visual_intent_and_unresolved_reason():
    """Legacy submit action, v2 visual_region labels, informative→informational intent_kind, bad reason_code."""
    raw = {
        "ui_state": {
            "state_id": "state_y",
            "screen_purpose": "demo",
            "presentation_scope": "full_screen",
            "screen_type": "form",
            "outcome_state_type": "neutral",
            "domain": "ecommerce",
            "visible_elements": [
                {
                    "element_id": "el_001",
                    "element_type": "not_a_real_llm_token",
                    "text": ["Label"],
                    "visual_region": "main_content",
                }
            ],
            "available_actions": [
                {
                    "action_id": "ac_001",
                    "action_type": "submit",
                    "text": ["Go"],
                    "action_priority": "primary",
                    "visual_region": "header",
                }
            ],
            "visible_feedback": [],
            "interaction_groups": [
                {
                    "group_id": "ig_001",
                    "group_type": "form",
                    "element_ids": ["el_001"],
                    "action_ids": ["ac_001"],
                    "feedback_ids": [],
                    "primary_action_id": "ac_001",
                    "group_evidence": [
                        {"evidence_type": "explicit_container", "description": "x"}
                    ],
                    "group_confidence": "high",
                }
            ],
        },
        "screen_intents": {
            "screen_behaviour_intents": [
                {
                    "source_group_id": "ig_001",
                    "intent_kind": "informative",
                    "intent_name": "read",
                    "local_user_goal": "read only",
                    "primary_action_id": None,
                    "commit_action_id": None,
                    "secondary_action_ids": [],
                    "selection_options": [],
                    "local_action_sequence_templates": [],
                    "required_input_element_ids": [],
                    "evidence_refs": [
                        {"evidence_type": "element_text", "source_id": "el_001"}
                    ],
                    "model_confidence": "high",
                }
            ],
            "unresolved_screen_groups": [
                {
                    "group_id": "ig_002",
                    "reason_code": "totally_unknown_backend_reason",
                    "details": "",
                }
            ],
        },
    }
    m = JointScreenUnderstandingResult.model_validate(raw)
    assert m.ui_state.visible_elements[0].element_type == "other"
    assert m.ui_state.visible_elements[0].visual_region == "main"
    assert m.ui_state.available_actions[0].action_type == "click"
    assert m.ui_state.available_actions[0].visual_region == "top_bar"
    assert m.screen_intents.screen_behaviour_intents[0].intent_kind == "informational"
    assert m.screen_intents.unresolved_screen_groups[0].reason_code == "schema_violation"
