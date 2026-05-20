"""Tests for PredEvaluationView and build_prediction_evaluation_view."""

from __future__ import annotations

from collections import Counter

from experiments.ui_state_extraction.services.evaluation_key_service import element_key
from experiments.ui_state_extraction.services.prediction_normalizer_service import (
    build_prediction_evaluation_view,
)

from tests.unit.test_ui_state_extraction_module2 import _login_raw_payload


def test_view_login_element_action_counts_align_with_keys() -> None:
    raw = _login_raw_payload()
    ui = raw["ui_state"]
    expected_el: Counter[tuple[str, str]] = Counter()
    for el in ui["visible_elements"]:
        ek = element_key(el)
        if ek:
            expected_el[ek] += 1
    view = build_prediction_evaluation_view(raw)
    assert dict(view.element_keys) == dict(expected_el)
    assert view.diagnostics.skipped_empty_key_element == 0


def test_view_email_value_primary_text_preserves_normalized_key() -> None:
    raw = _login_raw_payload()
    raw["ui_state"]["visible_elements"][0]["text"] = ["heyo@gmail.com"]
    raw_el = raw["ui_state"]["visible_elements"][0]
    view = build_prediction_evaluation_view(raw)
    k_expected = element_key(raw_el)
    assert k_expected is not None
    assert view.element_keys[k_expected] == 1


def test_view_skipped_empty_feedback_and_flags() -> None:
    raw = _login_raw_payload()
    raw["ui_state"]["visible_feedback"] = [{"feedback_id": "fb_bad", "feedback_type": "inline_error", "text": []}]
    view = build_prediction_evaluation_view(raw)
    assert view.diagnostics.skipped_empty_key_feedback == 1
    assert any("pred_feedback_key_missing" in x for x in view.diagnostics.prediction_auto_flags)


def test_prompt_fixed_style_screen_key_multiset() -> None:
    raw = _prompt_fixed_joint_raw_stub()
    view = build_prediction_evaluation_view(raw)

    expected_elements = [
        ("input", "email"),
        ("input", "password"),
        ("button", "sign-in"),
        ("link", "forgot-password"),
    ]
    for k in expected_elements:
        assert view.element_keys[k] == 1, f"missing element key {k!r}"

    expected_actions = [
        ("type", "email"),
        ("type", "password"),
        ("submit", "sign-in"),
        ("navigate", "forgot-password"),
    ]
    for k in expected_actions:
        assert view.action_keys[k] == 1, f"missing action key {k!r}"

    assert view.diagnostics.skipped_empty_key_element == 0


def _prompt_fixed_joint_raw_stub() -> dict:
    return {
        "ui_state": {
            "presentation_scope": "full_screen",
            "screen_type": "auth",
            "outcome_state_type": "neutral",
            "domain": "authentication",
            "visible_elements": [
                {"element_id": "e1", "element_type": "input", "text": ["Email"], "visual_region": "main"},
                {"element_id": "e2", "element_type": "input", "text": ["Password"], "visual_region": "main"},
                {"element_id": "e3", "element_type": "button", "text": ["Sign in"], "visual_region": "main"},
                {
                    "element_id": "e4",
                    "element_type": "link",
                    "text": ["Forgot password?"],
                    "visual_region": "main",
                },
            ],
            "available_actions": [
                {"action_id": "a1", "action_type": "type", "text": ["Email"], "visual_region": "main"},
                {"action_id": "a2", "action_type": "type", "text": ["Password"], "visual_region": "main"},
                {"action_id": "a3", "action_type": "submit", "text": ["Sign in"], "visual_region": "main"},
                {
                    "action_id": "a4",
                    "action_type": "navigate",
                    "text": ["Forgot password?"],
                    "visual_region": "main",
                },
            ],
            "visible_feedback": [],
            "interaction_groups": [
                {
                    "group_id": "ig1",
                    "group_type": "form",
                    "element_ids": ["e1", "e2", "e3", "e4"],
                    "action_ids": ["a1", "a2", "a3", "a4"],
                    "feedback_ids": [],
                    "primary_action_id": "a3",
                }
            ],
        },
        "screen_intents": {
            "screen_behaviour_intents": [
                {
                    "source_group_id": "ig1",
                    "intent_kind": "submission",
                    "primary_action_id": "a3",
                    "commit_action_id": "a3",
                    "secondary_action_ids": ["a1", "a2"],
                    "required_input_element_ids": ["e1", "e2"],
                    "evidence_refs": [{"evidence_type": "action_text", "source_id": "a3"}],
                    "local_action_sequence_templates": [
                        {
                            "steps": [],
                            "outcome_prediction_allowed": False,
                        }
                    ],
                }
            ]
        },
    }
