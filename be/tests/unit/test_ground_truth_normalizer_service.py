"""Tests for GT evaluation view (multiset keys, Sprint 5)."""

from __future__ import annotations

from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
    ImageMetaInRawOutput,
    ModelCallMeta,
)
from experiments.ui_state_extraction.services.evaluation_key_service import action_key, element_key
from experiments.ui_state_extraction.services.ground_truth_normalizer_service import (
    build_gt_evaluation_view,
)
from experiments.ui_state_extraction.services.temp_ground_truth_builder_service import (
    build_temp_ground_truth_from_raw,
)


def _signup_dual_intents_raw() -> dict:
    """Signup screen with submission + navigation intents (S07-style acceptance fixture)."""
    return {
        "ui_state": {
            "state_id": "state_exp_auth_signup_s07",
            "screen_purpose": "Sign up flow",
            "presentation_scope": "full_screen",
            "screen_type": "auth",
            "outcome_state_type": "neutral",
            "domain": "authentication",
            "visible_elements": [
                {
                    "element_id": "e1",
                    "element_type": "input",
                    "text": ["Email"],
                    "role_hint": "required_input",
                    "visual_region": "main",
                },
                {
                    "element_id": "e2",
                    "element_type": "input",
                    "text": ["Password"],
                    "role_hint": "required_input",
                    "visual_region": "main",
                },
                {
                    "element_id": "e3",
                    "element_type": "button",
                    "text": ["Create account"],
                    "role_hint": "primary_action",
                    "visual_region": "main",
                },
                {
                    "element_id": "e4",
                    "element_type": "link",
                    "text": ["Already have an account? Sign in"],
                    "visual_region": "main",
                },
            ],
            "available_actions": [
                {
                    "action_id": "a1",
                    "action_type": "type",
                    "text": ["Email"],
                    "visual_region": "main",
                },
                {
                    "action_id": "a2",
                    "action_type": "type",
                    "text": ["Password"],
                    "visual_region": "main",
                },
                {
                    "action_id": "a3",
                    "action_type": "submit",
                    "text": ["Create account"],
                    "visual_region": "main",
                },
                {
                    "action_id": "a4",
                    "action_type": "navigate",
                    "text": ["Already have an account? Sign in"],
                    "visual_region": "main",
                },
            ],
            "visible_feedback": [],
            "interaction_groups": [
                {
                    "group_id": "ig1",
                    "group_type": "form",
                    "group_label": "Sign up form",
                    "element_ids": ["e1", "e2", "e3", "e4"],
                    "action_ids": ["a1", "a2", "a3", "a4"],
                    "feedback_ids": [],
                    "primary_action_id": "a3",
                    "group_evidence": [],
                    "group_confidence": "high",
                },
            ],
        },
        "screen_intents": {
            "screen_behaviour_intents": [
                {
                    "source_group_id": "ig1",
                    "intent_kind": "submission",
                    "intent_name": "Submit signup",
                    "local_user_goal": "Create account",
                    "primary_action_id": "a3",
                    "commit_action_id": "a3",
                    "secondary_action_ids": ["a1", "a2"],
                    "required_input_element_ids": ["e1", "e2"],
                    "selection_options": [],
                    "evidence_refs": [{"evidence_type": "action_text", "source_id": "a3"}],
                    "local_action_sequence_templates": [
                        {
                            "sequence_name": "fill_and_submit_signup",
                            "steps": [],
                            "outcome_prediction_allowed": False,
                        }
                    ],
                    "model_confidence": "high",
                },
                {
                    "source_group_id": "ig1",
                    "intent_kind": "navigation",
                    "intent_name": "Navigate to sign in",
                    "local_user_goal": "Existing user sign in",
                    "primary_action_id": "a4",
                    "commit_action_id": "a4",
                    "secondary_action_ids": [],
                    "required_input_element_ids": [],
                    "selection_options": [],
                    "evidence_refs": [{"evidence_type": "action_text", "source_id": "a4"}],
                    "local_action_sequence_templates": [
                        {
                            "sequence_name": "navigate_secondary",
                            "steps": [],
                            "outcome_prediction_allowed": False,
                        }
                    ],
                    "model_confidence": "high",
                },
            ],
            "unresolved_screen_groups": [],
        },
    }


def test_gt_view_signup_dual_intents_acceptance_s07_style() -> None:
    raw = _signup_dual_intents_raw()
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="s07_fixture",
            relative_path="signup/s07.png",
            stem="s07",
            extension=".png",
        ),
        model_call=ModelCallMeta(status="success", created_at=""),
        raw_model_output=raw,
    )
    gt = build_temp_ground_truth_from_raw(doc, source_raw_output_path="raw.json", validate_joint_schema=True)

    submission_key = ("submission", ("submit", "create-account"))
    navigation_key = ("navigation", ("navigate", "already-have-an-account-sign-in"))

    view = build_gt_evaluation_view(gt)
    assert view.intent_keys[submission_key] == 1
    assert view.intent_keys[navigation_key] == 1
    assert view.action_keys[("submit", "create-account")] == 1
    assert view.action_keys[("navigate", "already-have-an-account-sign-in")] == 1

    assert view.screen_fields.presentation_scope == "full_screen"
    assert view.screen_fields.screen_type == "auth"
    assert view.screen_fields.outcome_state_type == "neutral"

    expected_el_keys: dict[tuple[str, str], int] = {}
    for el in gt.elements:
        ek = element_key(el)
        if ek:
            expected_el_keys[ek] = expected_el_keys.get(ek, 0) + 1
    assert dict(view.element_keys) == expected_el_keys

    expected_ac_keys: dict[tuple[str, str], int] = {}
    for ac in gt.actions:
        ak = action_key(ac)
        if ak:
            expected_ac_keys[ak] = expected_ac_keys.get(ak, 0) + 1
    assert dict(view.action_keys) == expected_ac_keys
