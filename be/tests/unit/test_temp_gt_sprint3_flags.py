"""Sprint 3: temp GT builder key_missing flags, label-first heuristics, evaluation key summary."""

from __future__ import annotations

from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
    ImageMetaInRawOutput,
    ModelCallMeta,
)
from experiments.ui_state_extraction.services.control_label_first_heuristics import (
    control_label_first_flags_for_element,
)
from experiments.ui_state_extraction.services.evaluation_key_service import summarize_evaluation_keys
from experiments.ui_state_extraction.services.ground_truth_normalizer_service import (
    build_gt_evaluation_view,
)
from experiments.ui_state_extraction.services.temp_ground_truth_builder_service import (
    build_temp_ground_truth_from_raw,
)

from tests.unit.test_ui_state_extraction_module2 import _login_raw_payload


def test_control_label_first_email_and_maybe_missing() -> None:
    flags = control_label_first_flags_for_element(
        "gt_el_001",
        ["heyo@gmail.com"],
        element_type="input",
        role_hint="required_input",
    )
    assert "control_primary_text_looks_like_value:gt_el_001" in flags
    assert "control_label_maybe_missing:gt_el_001" in flags


def test_control_label_first_masked() -> None:
    flags = control_label_first_flags_for_element(
        "gt_el_002",
        ["....."],
        element_type="password_field",
        role_hint="required_input",
    )
    assert "control_primary_text_masked_value:gt_el_002" in flags
    assert "control_label_maybe_missing:gt_el_002" in flags


def test_builder_flags_email_in_control() -> None:
    raw = _login_raw_payload()
    raw["ui_state"]["visible_elements"][0]["text"] = ["heyo@gmail.com"]
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="test",
            relative_path="x.png",
            stem="x",
            extension=".png",
        ),
        model_call=ModelCallMeta(status="success", created_at=""),
        raw_model_output=raw,
    )
    gt = build_temp_ground_truth_from_raw(
        doc,
        source_raw_output_path="raw.json",
        validate_joint_schema=True,
    )
    flags = gt.conversion_report.auto_flags
    assert any(f.startswith("control_primary_text_looks_like_value:gt_el_001") for f in flags)
    assert any(f.startswith("element_key_missing:") for f in flags) is False


def test_summarize_evaluation_keys_login_fixture() -> None:
    raw = _login_raw_payload()
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
    gt = build_temp_ground_truth_from_raw(doc, source_raw_output_path="raw.json", validate_joint_schema=True)
    summary = summarize_evaluation_keys(gt)
    assert summary["elements"]["gt_el_001"] == "(input, email)"
    assert summary["actions"]["gt_ac_003"] is not None
    assert summary["intents"]["gt_intent_001"] is not None

    gt_view = build_gt_evaluation_view(gt)
    assert sum(gt_view.intent_keys.values()) == len(gt.screen_intents)
    assert gt_view.screen_fields.screen_type == "auth"
