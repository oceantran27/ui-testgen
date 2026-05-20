"""Unit tests for experiments.ui_state_extraction module 2 (temp ground truth builder)."""

from __future__ import annotations

from pathlib import Path

from experiments.ui_state_extraction.config import PACKAGE_ROOT
from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
    ImageMetaInRawOutput,
    ModelCallMeta,
)
from experiments.ui_state_extraction.services.temp_ground_truth_builder_service import (
    build_temp_ground_truth_from_raw,
)
from experiments.ui_state_extraction.services.temp_ground_truth_persistence_service import (
    temp_gt_file_path,
)
from experiments.ui_state_extraction.services.text_normalization_service import (
    normalize_for_match,
    normalized_join_contains,
    text_matches,
)


def test_normalize_for_match_strips_punct_and_space() -> None:
    assert normalize_for_match('  Hello,  World!  ') == "hello world"
    assert normalize_for_match("Tiếng Việt.") == "tiếng việt"


def test_text_matches_bidirectional() -> None:
    assert text_matches("enter email address", "Email address") is True
    assert text_matches("a", "b") is False


def test_normalized_join_contains() -> None:
    assert normalized_join_contains("Enter Email address", "email") is True


def test_temp_gt_file_path_mirror() -> None:
    base = PACKAGE_ROOT / "temp_ground_truth"
    p = temp_gt_file_path(base, "auth/login/x.png", "x")
    assert p.relative_to(PACKAGE_ROOT).as_posix() == "temp_ground_truth/auth/login/x.temp_gt.json"


def _login_raw_payload() -> dict:
    """Shape aligned with JointScreenUnderstandingResult (spec §14)."""
    return {
        "ui_state": {
            "state_id": "state_exp_auth_login_login_empty",
            "screen_purpose": "User logs in",
            "presentation_scope": "full_screen",
            "screen_type": "auth",
            "outcome_state_type": "neutral",
            "domain": "authentication",
            "visible_elements": [
                {
                    "element_id": "el_001",
                    "element_type": "input",
                    "text": ["Email"],
                    "role_hint": "required_input",
                    "visual_region": "main",
                },
                {
                    "element_id": "el_002",
                    "element_type": "input",
                    "text": ["Password"],
                    "role_hint": "required_input",
                    "visual_region": "main",
                },
                {
                    "element_id": "el_003",
                    "element_type": "button",
                    "text": ["Login"],
                    "role_hint": "primary_action",
                    "visual_region": "main",
                },
            ],
            "available_actions": [
                {
                    "action_id": "ac_001",
                    "action_type": "type",
                    "text": ["Enter Email"],
                    "action_priority": "primary",
                    "visual_region": "main",
                },
                {
                    "action_id": "ac_002",
                    "action_type": "type",
                    "text": ["Enter Password"],
                    "action_priority": "primary",
                    "visual_region": "main",
                },
                {
                    "action_id": "ac_003",
                    "action_type": "click",
                    "text": ["Login"],
                    "action_priority": "primary",
                    "visual_region": "main",
                },
            ],
            "visible_feedback": [],
            "interaction_groups": [
                {
                    "group_id": "ig_001",
                    "group_type": "form",
                    "group_label": "Login Form",
                    "element_ids": ["el_001", "el_002", "el_003"],
                    "action_ids": ["ac_001", "ac_002", "ac_003"],
                    "feedback_ids": [],
                    "primary_action_id": "ac_003",
                    "group_evidence": [],
                    "group_confidence": "high",
                }
            ],
        },
        "screen_intents": {
            "screen_behaviour_intents": [
                {
                    "source_group_id": "ig_001",
                    "intent_kind": "submission",
                    "intent_name": "Submit login",
                    "local_user_goal": "Sign in",
                    "primary_action_id": "ac_003",
                    "commit_action_id": "ac_003",
                    "secondary_action_ids": ["ac_001", "ac_002"],
                    "selection_options": [],
                    "required_input_element_ids": ["el_001", "el_002"],
                    "evidence_refs": [{"evidence_type": "action_text", "source_id": "ac_003"}],
                    "local_action_sequence_templates": [
                        {
                            "sequence_name": "enter credentials and login",
                            "steps": [
                                {
                                    "step_type": "enter_input",
                                    "source_action_id": "ac_001",
                                    "source_element_id": "el_001",
                                },
                                {
                                    "step_type": "enter_input",
                                    "source_action_id": "ac_002",
                                    "source_element_id": "el_002",
                                },
                                {
                                    "step_type": "invoke_action",
                                    "source_action_id": "ac_003",
                                    "source_element_id": "el_003",
                                },
                            ],
                            "outcome_prediction_allowed": False,
                        }
                    ],
                    "model_confidence": "high",
                }
            ],
            "unresolved_screen_groups": [],
        },
    }


def test_builder_login_example_grounding_and_intents() -> None:
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="exp_auth_login_login_empty",
            relative_path="auth/login/login_empty.png",
            filename="login_empty.png",
            stem="login_empty",
            extension=".png",
            source_path="/dataset/auth/login/login_empty.png",
        ),
        model_call=ModelCallMeta(status="success", created_at=""),
        raw_model_output=_login_raw_payload(),
    )
    gt = build_temp_ground_truth_from_raw(
        doc,
        source_raw_output_path="raw_outputs/auth/login/login_empty.raw.json",
        validate_joint_schema=True,
    )
    assert gt.elements[0].anchor_texts == ["Email"]
    assert gt.actions[0].grounded_element_id == "gt_el_001"
    assert gt.actions[0].anchor_texts == ["Email"]
    assert gt.actions[2].grounded_element_id == "gt_el_003"
    assert gt.screen_intents[0].source_group_id == "gt_ig_001"
    assert gt.screen_intents[0].evidence_target_ids == ["gt_ac_003"]
    assert len(gt.screen_intents[0].expected_steps) == 3
    assert gt.annotation_meta.review_priority == "low"
    assert gt.conversion_report.counts.elements == 3


def test_builder_orphan_element_flag() -> None:
    raw = _login_raw_payload()
    raw["ui_state"]["interaction_groups"] = [
        {
            "group_id": "ig_001",
            "group_type": "form",
            "element_ids": ["el_001", "el_002"],
            "action_ids": ["ac_001", "ac_002", "ac_003"],
            "feedback_ids": [],
            "primary_action_id": "ac_003",
            "group_evidence": [],
            "group_confidence": "high",
        }
    ]
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="i",
            relative_path="a.png",
            stem="a",
            extension=".png",
        ),
        model_call=ModelCallMeta(status="success", created_at=""),
        raw_model_output=raw,
    )
    gt = build_temp_ground_truth_from_raw(
        doc,
        source_raw_output_path="raw_outputs/a.raw.json",
        validate_joint_schema=True,
    )
    assert any("orphan_element" in f for f in gt.conversion_report.auto_flags)
