"""Unit tests for experiments.ui_state_extraction.services.evaluation_key_service."""

from __future__ import annotations

from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
    PredActionUnit,
    PredElementUnit,
    PredFeedbackUnit,
    PredIntentUnit,
)
from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
    ActionRecord,
    ElementRecord,
    FeedbackRecord,
    ReviewBlock,
    ScreenIntentRecord,
)
from experiments.ui_state_extraction.services.evaluation_key_service import (
    action_key,
    build_action_lookup_by_id,
    element_key,
    feedback_key,
    has_evaluable_key,
    intent_key,
    normalize_label,
    primary_text,
)


def test_normalize_label_light_punctuation_and_hyphens() -> None:
    assert normalize_label("Forgot password?") == "forgot-password"
    assert normalize_label("Need an account? Sign up") == "need-an-account-sign-up"
    assert normalize_label("  a  b  ") == "a-b"
    assert normalize_label("") is None
    assert normalize_label(None) is None
    assert normalize_label("  ") is None


def test_normalize_label_vietnamese() -> None:
    assert normalize_label("  Đăng   nhập  ") == "đăng-nhập"


def test_primary_text_first_non_empty() -> None:
    assert primary_text(None) is None
    assert primary_text([]) is None
    assert primary_text(["", "  ", "x"]) == "x"
    assert primary_text(["  hello ", "world"]) == "hello"


def test_element_key_gt_and_pred() -> None:
    g = ElementRecord(
        gt_element_id="gt_el_001",
        source_model_element_id="m1",
        anchor_texts=["Email"],
        element_type="text_field",
        review=ReviewBlock(),
    )
    assert element_key(g) == ("text_field", "email")

    p = PredElementUnit(pred_element_id="p1", anchor_texts=["Email"], element_type="text_field")
    assert element_key(p) == ("text_field", "email")


def test_element_key_raw_dict_text_when_anchors_empty() -> None:
    d = {
        "element_id": "e1",
        "element_type": "button",
        "text": ["  Sign in  "],
        "anchor_texts": [],
    }
    assert element_key(d) == ("button", "sign-in")


def test_action_key_gt_action_record() -> None:
    a = ActionRecord(
        gt_action_id="gt_ac_001",
        source_model_action_id="a_raw",
        anchor_texts=["Continue"],
        source_model_texts=[],
        action_type="click",
        review=ReviewBlock(),
    )
    assert action_key(a) == ("click", "continue")


def test_action_key_prefers_source_model_texts_over_grounded_anchor() -> None:
    """GT actions: model text beats grounded anchor (avoid module-2 grounding skew vs pred keys)."""
    a = ActionRecord(
        gt_action_id="gt_ac_002",
        source_model_action_id="m_act",
        anchor_texts=["email"],
        source_model_texts=["Enter Email"],
        action_type="type",
        review=ReviewBlock(),
    )
    assert action_key(a) == ("type", "enter-email")


def test_action_key_pred_source_model_texts_fallback() -> None:
    p = PredActionUnit(
        pred_action_id="p1",
        source_model_texts=["OK"],
        anchor_texts=[],
        action_type="confirm",
    )
    assert action_key(p) == ("confirm", "ok")


def test_feedback_key() -> None:
    f = FeedbackRecord(
        gt_feedback_id="gt_fb_001",
        source_model_feedback_id="f1",
        anchor_texts=["Error!"],
        feedback_type="inline_error",
        review=ReviewBlock(),
    )
    assert feedback_key(f) == ("inline_error", "error")


def test_build_action_lookup_by_id_indexes_all_ids() -> None:
    a = ActionRecord(
        gt_action_id="gt_ac_001",
        source_model_action_id="model_a",
        anchor_texts=["x"],
        source_model_texts=[],
        action_type="click",
        review=ReviewBlock(),
    )
    lut = build_action_lookup_by_id([a])
    assert lut["gt_ac_001"] is a
    assert lut["model_a"] is a


def test_build_action_lookup_raw_dict() -> None:
    raw = {"action_id": "ac1", "action_type": "tap", "text": ["Go"], "anchor_texts": []}
    lut = build_action_lookup_by_id([raw])
    assert lut["ac1"] is raw


def test_intent_key_gt_screen_intent_and_commit() -> None:
    ac = ActionRecord(
        gt_action_id="gt_ac_001",
        source_model_action_id="m1",
        anchor_texts=["Submit"],
        source_model_texts=[],
        action_type="submit",
        review=ReviewBlock(),
    )
    lut = build_action_lookup_by_id([ac])
    intent = ScreenIntentRecord(
        gt_intent_id="gt_intent_001",
        source_model_index=0,
        intent_kind="complete_flow",
        commit_action_id="gt_ac_001",
        review=ReviewBlock(),
    )
    assert intent_key(intent, lut) == ("complete_flow", ("submit", "submit"))


def test_intent_key_pred_uses_commit_pred_action_id() -> None:
    ac = PredActionUnit(
        pred_action_id="pa1",
        anchor_texts=["Done"],
        action_type="confirm",
    )
    lut = build_action_lookup_by_id([ac])
    intent = PredIntentUnit(
        pred_intent_index=0,
        intent_kind="finish",
        source_pred_group_id="",
        commit_pred_action_id="pa1",
    )
    assert intent_key(intent, lut) == ("finish", ("confirm", "done"))


def test_intent_key_missing_commit_returns_none() -> None:
    ac = ActionRecord(
        gt_action_id="gt_ac_001",
        source_model_action_id="m1",
        anchor_texts=["x"],
        source_model_texts=[],
        action_type="click",
        review=ReviewBlock(),
    )
    lut = build_action_lookup_by_id([ac])
    intent = ScreenIntentRecord(
        gt_intent_id="gt_intent_001",
        source_model_index=0,
        intent_kind="complete_flow",
        commit_action_id=None,
        review=ReviewBlock(),
    )
    assert intent_key(intent, lut) is None


def test_has_evaluable_key() -> None:
    empty_el = ElementRecord(
        gt_element_id="gt_el_001",
        source_model_element_id="m1",
        anchor_texts=[],
        review=ReviewBlock(),
    )
    assert not has_evaluable_key(empty_el, kind="element")

    ok_el = ElementRecord(
        gt_element_id="gt_el_002",
        source_model_element_id="m2",
        anchor_texts=["Hi"],
        review=ReviewBlock(),
    )
    assert has_evaluable_key(ok_el, kind="element")
