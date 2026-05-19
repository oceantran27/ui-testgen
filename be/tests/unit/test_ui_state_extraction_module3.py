"""Unit tests for experiments.ui_state_extraction module 3 (evaluation)."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
    ImageMetaInRawOutput,
    ModelCallMeta,
)
from experiments.ui_state_extraction.services.metric_calculation_service import (
    evaluate_pair,
    micro_macro_from_per_image,
)
from experiments.ui_state_extraction.services.prediction_normalizer_service import (
    normalize_raw_model_output,
)
from experiments.ui_state_extraction.services.temp_ground_truth_builder_service import (
    build_temp_ground_truth_from_raw,
)
from experiments.ui_state_extraction.services.text_normalization_service import normalize_for_match

# Reuse login payload from module 2 tests
from tests.unit.test_ui_state_extraction_module2 import _login_raw_payload


def test_normalize_text_adds_parentheses_stripping() -> None:
    assert normalize_for_match("Hello (test)") == "hello test"


def test_module3_evaluate_login_fixture_perfect_match() -> None:
    raw = _login_raw_payload()
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="exp_auth_login_login_empty",
            relative_path="auth/login/login_empty.png",
            filename="login_empty.png",
            stem="login_empty",
            extension=".png",
        ),
        model_call=ModelCallMeta(status="success", created_at=""),
        raw_model_output=raw,
    )
    gt = build_temp_ground_truth_from_raw(
        doc,
        source_raw_output_path="raw_outputs/auth/login/login_empty.raw.json",
        validate_joint_schema=True,
    )

    pred = normalize_raw_model_output(raw)
    res = evaluate_pair(
        pred,
        gt,
        raw,
        group_jaccard_threshold=0.6,
        include_debug=True,
    )
    assert res.element_metrics.f1 == 1.0
    assert res.element_metrics.text_grounded_pred_count == len(pred.elements)
    assert res.element_metrics.pred_empty_anchor_element_count == 0
    assert res.action_metrics.f1 == 1.0
    assert res.action_metrics.action_grounding_accuracy == 1.0
    assert res.screen_metrics.accuracy == 1.0
    assert res.group_metrics.matched_count >= 1
    assert res.intent_metrics.matched_count >= 1
    micro, macro = micro_macro_from_per_image([res])
    assert micro.get("element_f1") == 1.0
    assert micro.get("action_f1") == 1.0


def test_module3_element_metrics_exclude_empty_anchors() -> None:
    """P/R/F1 use text-grounded elements only; empty-anchor rows are counted separately."""
    from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
        PredElementUnit,
        PredScreenUnit,
        PredictionEvaluationBundle,
    )
    from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
        AnnotationMeta,
        ElementRecord,
        ImageMetaInTempGt,
        ScreenBlock,
        TempGroundTruthDocument,
    )

    pred = PredictionEvaluationBundle(
        screen=PredScreenUnit(),
        elements=[
            PredElementUnit(pred_element_id="p0", anchor_texts=[]),
            PredElementUnit(pred_element_id="p1", anchor_texts=["hello"]),
        ],
    )
    gt = TempGroundTruthDocument(
        schema_version="temp_gt_test_v1",
        annotation_meta=AnnotationMeta(source_raw_output_path="raw/x.json"),
        image=ImageMetaInTempGt(image_id="img_t", relative_path="t.png"),
        screen=ScreenBlock(),
        elements=[
            ElementRecord(
                gt_element_id="gt_el_0",
                source_model_element_id="p0",
                anchor_texts=[],
            ),
            ElementRecord(
                gt_element_id="gt_el_1",
                source_model_element_id="p1",
                anchor_texts=["Hello"],
            ),
        ],
    )
    raw: dict = {"ui_state": {"visible_elements": [], "interaction_groups": []}, "screen_intents": {}}
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    assert res.element_metrics.pred_empty_anchor_element_count == 1
    assert res.element_metrics.gt_empty_anchor_element_count == 1
    assert res.element_metrics.empty_anchor_element_delta == 0
    assert res.element_metrics.text_grounded_pred_count == 1
    assert res.element_metrics.text_grounded_gt_count == 1
    assert res.element_metrics.text_grounded_matched_count == 1
    assert res.element_metrics.matched_count == 1
    assert res.element_metrics.precision == 1.0
    assert res.element_metrics.recall == 1.0
    assert res.element_metrics.f1 == 1.0
    assert res.consistency_metrics.hallucinated_element_count == 0


def test_module3_gt_empty_anchor_does_not_hurt_text_grounded_recall() -> None:
    """Extra GT element with no anchor is excluded from recall denominator."""
    from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
        PredElementUnit,
        PredScreenUnit,
        PredictionEvaluationBundle,
    )
    from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
        AnnotationMeta,
        ElementRecord,
        ImageMetaInTempGt,
        ScreenBlock,
        TempGroundTruthDocument,
    )

    pred = PredictionEvaluationBundle(
        screen=PredScreenUnit(),
        elements=[PredElementUnit(pred_element_id="p1", anchor_texts=["Foo"])],
    )
    gt = TempGroundTruthDocument(
        schema_version="temp_gt_test_v1",
        annotation_meta=AnnotationMeta(source_raw_output_path="raw/x.json"),
        image=ImageMetaInTempGt(image_id="img_t2", relative_path="t2.png"),
        screen=ScreenBlock(),
        elements=[
            ElementRecord(
                gt_element_id="gt_el_ghost",
                source_model_element_id="none",
                anchor_texts=[],
            ),
            ElementRecord(
                gt_element_id="gt_el_1",
                source_model_element_id="p1",
                anchor_texts=["foo"],
            ),
        ],
    )
    raw: dict = {"ui_state": {"visible_elements": [], "interaction_groups": []}, "screen_intents": {}}
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    assert res.element_metrics.gt_empty_anchor_element_count == 1
    assert res.element_metrics.text_grounded_gt_count == 1
    assert res.element_metrics.recall == 1.0


def test_module3_writes_reports_tmp(tmp_path: Path) -> None:
    from experiments.ui_state_extraction import config as m3cfg
    from experiments.ui_state_extraction.schemas.evaluation_metric_schema import DatasetSummary
    from experiments.ui_state_extraction.services.evaluation_report_service import (
        metrics_summary_csv_rows,
        per_image_csv_rows,
        write_csv,
        write_evaluation_summary_json,
        write_markdown_report,
        write_per_image_json,
    )

    raw = _login_raw_payload()
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="i1",
            relative_path="a/b.png",
            filename="b.png",
        ),
        model_call=ModelCallMeta(status="success", created_at=""),
        raw_model_output=raw,
    )
    gt = build_temp_ground_truth_from_raw(
        doc,
        source_raw_output_path="raw/x.raw.json",
        validate_joint_schema=True,
    )

    pred = normalize_raw_model_output(raw)
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    micro, macro = micro_macro_from_per_image([res])
    out = tmp_path / "eval"
    out.mkdir()
    ds = DatasetSummary(
        total_raw_outputs=1,
        total_ground_truth_files=1,
        total_matched_pairs=1,
        total_evaluated=1,
        total_skipped=0,
    )
    write_evaluation_summary_json(
        out / "evaluation_summary.json",
        schema_version=m3cfg.EVALUATION_SUMMARY_SCHEMA_VERSION,
        dataset_summary=ds,
        micro=micro,
        macro=macro,
        skipped_items=[],
    )
    write_per_image_json(out / "evaluation_per_image.json", [res])
    write_csv(out / "evaluation_summary.csv", metrics_summary_csv_rows(micro, macro, count=1))
    write_csv(out / "evaluation_per_image.csv", per_image_csv_rows([res]))
    write_markdown_report(out / "evaluation_report.md", dataset_summary=ds, micro=micro)

    assert (out / "evaluation_summary.json").is_file()
    summary = json.loads((out / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert summary.get("schema_version") == m3cfg.EVALUATION_SUMMARY_SCHEMA_VERSION
    assert "aggregate_metrics" in summary


def test_module3_required_input_ignores_empty_anchor_gt_refs() -> None:
    """GT required_input may list empty-anchor elements; they must not penalize F1."""
    from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
        PredElementUnit,
        PredGroupUnit,
        PredIntentUnit,
        PredScreenUnit,
        PredictionEvaluationBundle,
    )
    from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
        AnnotationMeta,
        ElementRecord,
        GroupRecord,
        ImageMetaInTempGt,
        ScreenBlock,
        ScreenIntentRecord,
        TempGroundTruthDocument,
    )

    pred = PredictionEvaluationBundle(
        screen=PredScreenUnit(),
        elements=[PredElementUnit(pred_element_id="p_ok", anchor_texts=["field"])],
        groups=[
            PredGroupUnit(pred_group_id="g1", member_pred_element_ids=["p_ok"]),
        ],
        intents=[
            PredIntentUnit(
                pred_intent_index=0,
                intent_kind="form_fill",
                source_pred_group_id="g1",
                required_pred_element_ids=["p_ok"],
            ),
        ],
    )
    gt = TempGroundTruthDocument(
        schema_version="temp_gt_test_v1",
        annotation_meta=AnnotationMeta(source_raw_output_path="raw/x.json"),
        image=ImageMetaInTempGt(image_id="img_ri", relative_path="ri.png"),
        screen=ScreenBlock(),
        elements=[
            ElementRecord(
                gt_element_id="gt_ghost",
                source_model_element_id="x",
                anchor_texts=[],
            ),
            ElementRecord(
                gt_element_id="gt_ok",
                source_model_element_id="p_ok",
                anchor_texts=["field"],
            ),
        ],
        groups=[
            GroupRecord(
                gt_group_id="gg1",
                source_model_group_id="g1",
                member_element_ids=["gt_ghost", "gt_ok"],
            ),
        ],
        screen_intents=[
            ScreenIntentRecord(
                gt_intent_id="int1",
                intent_kind="form_fill",
                source_group_id="gg1",
                required_input_element_ids=["gt_ghost", "gt_ok"],
            ),
        ],
    )
    raw: dict = {"ui_state": {"visible_elements": [], "interaction_groups": []}, "screen_intents": {}}
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    assert res.intent_metrics.matched_count == 1
    assert res.intent_metrics.required_input_f1 == 1.0
    assert res.intent_metrics.required_input_empty_anchor_excluded_gt_refs == 1


def test_module3_feedback_related_ignores_empty_anchor_refs() -> None:
    from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
        PredElementUnit,
        PredFeedbackUnit,
        PredScreenUnit,
        PredictionEvaluationBundle,
    )
    from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
        AnnotationMeta,
        ElementRecord,
        FeedbackRecord,
        ImageMetaInTempGt,
        ScreenBlock,
        TempGroundTruthDocument,
    )

    pred = PredictionEvaluationBundle(
        screen=PredScreenUnit(),
        elements=[PredElementUnit(pred_element_id="p1", anchor_texts=["a"])],
        feedback=[
            PredFeedbackUnit(
                pred_feedback_id="f1",
                anchor_texts=["err"],
                related_pred_element_ids=["p1"],
            ),
        ],
    )
    gt = TempGroundTruthDocument(
        schema_version="temp_gt_test_v1",
        annotation_meta=AnnotationMeta(source_raw_output_path="raw/x.json"),
        image=ImageMetaInTempGt(image_id="img_fb", relative_path="fb.png"),
        screen=ScreenBlock(),
        elements=[
            ElementRecord(gt_element_id="gt_ghost", source_model_element_id="x", anchor_texts=[]),
            ElementRecord(gt_element_id="gt_a", source_model_element_id="p1", anchor_texts=["a"]),
        ],
        feedback=[
            FeedbackRecord(
                gt_feedback_id="gf1",
                source_model_feedback_id="f1",
                anchor_texts=["err"],
                related_element_ids=["gt_ghost", "gt_a"],
            ),
        ],
    )
    raw: dict = {"ui_state": {"visible_elements": [], "interaction_groups": []}, "screen_intents": {}}
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    assert res.feedback_metrics.matched_count == 1
    assert res.feedback_metrics.feedback_related_element_accuracy == 1.0
    assert res.feedback_metrics.feedback_related_empty_anchor_excluded_gt_refs == 1


def test_module3_group_membership_ignores_empty_anchor_members() -> None:
    from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
        PredElementUnit,
        PredGroupUnit,
        PredScreenUnit,
        PredictionEvaluationBundle,
    )
    from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
        AnnotationMeta,
        ElementRecord,
        GroupRecord,
        ImageMetaInTempGt,
        ScreenBlock,
        TempGroundTruthDocument,
    )

    pred = PredictionEvaluationBundle(
        screen=PredScreenUnit(),
        elements=[PredElementUnit(pred_element_id="p1", anchor_texts=["a"])],
        groups=[
            PredGroupUnit(
                pred_group_id="pg1",
                member_pred_element_ids=["p1"],
            ),
        ],
    )
    gt = TempGroundTruthDocument(
        schema_version="temp_gt_test_v1",
        annotation_meta=AnnotationMeta(source_raw_output_path="raw/x.json"),
        image=ImageMetaInTempGt(image_id="img_gr", relative_path="gr.png"),
        screen=ScreenBlock(),
        elements=[
            ElementRecord(gt_element_id="gt_ghost", source_model_element_id="x", anchor_texts=[]),
            ElementRecord(gt_element_id="gt_a", source_model_element_id="p1", anchor_texts=["a"]),
        ],
        groups=[
            GroupRecord(
                gt_group_id="gg1",
                source_model_group_id="pg1",
                member_element_ids=["gt_ghost", "gt_a"],
                member_action_ids=[],
                member_feedback_ids=[],
            ),
        ],
    )
    raw: dict = {"ui_state": {"visible_elements": [], "interaction_groups": []}, "screen_intents": {}}
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    assert res.group_metrics.matched_count == 1
    assert res.group_metrics.group_membership_f1 == 1.0
    assert res.group_metrics.group_membership_empty_anchor_excluded_gt_refs == 1


def test_module3_step_metric_skips_empty_anchor_element() -> None:
    from experiments.ui_state_extraction.schemas.evaluation_unit_schema import (
        PredElementUnit,
        PredExpectedStepUnit,
        PredGroupUnit,
        PredIntentUnit,
        PredScreenUnit,
        PredictionEvaluationBundle,
    )
    from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
        AnnotationMeta,
        ElementRecord,
        ExpectedStepRecord,
        GroupRecord,
        ImageMetaInTempGt,
        ScreenBlock,
        ScreenIntentRecord,
        TempGroundTruthDocument,
    )

    pred = PredictionEvaluationBundle(
        screen=PredScreenUnit(),
        elements=[PredElementUnit(pred_element_id="p1", anchor_texts=["a"])],
        groups=[PredGroupUnit(pred_group_id="g1", member_pred_element_ids=["p1"])],
        intents=[
            PredIntentUnit(
                pred_intent_index=0,
                intent_kind="form_fill",
                source_pred_group_id="g1",
                expected_steps=[
                    PredExpectedStepUnit(
                        step_type="tap",
                        source_pred_action_id=None,
                        source_pred_element_id="p1",
                    ),
                ],
            ),
        ],
    )
    gt = TempGroundTruthDocument(
        schema_version="temp_gt_test_v1",
        annotation_meta=AnnotationMeta(source_raw_output_path="raw/x.json"),
        image=ImageMetaInTempGt(image_id="img_st", relative_path="st.png"),
        screen=ScreenBlock(),
        elements=[
            ElementRecord(gt_element_id="gt_ghost", source_model_element_id="x", anchor_texts=[]),
            ElementRecord(gt_element_id="gt_a", source_model_element_id="p1", anchor_texts=["a"]),
        ],
        groups=[
            GroupRecord(
                gt_group_id="gg1",
                source_model_group_id="g1",
                member_element_ids=["gt_a"],
            ),
        ],
        screen_intents=[
            ScreenIntentRecord(
                gt_intent_id="int1",
                intent_kind="form_fill",
                source_group_id="gg1",
                expected_steps=[
                    ExpectedStepRecord(
                        step_type="tap",
                        source_action_id=None,
                        source_element_id="gt_ghost",
                    ),
                    ExpectedStepRecord(
                        step_type="tap",
                        source_action_id=None,
                        source_element_id="gt_a",
                    ),
                ],
            ),
        ],
    )
    raw: dict = {"ui_state": {"visible_elements": [], "interaction_groups": []}, "screen_intents": {}}
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    assert res.intent_metrics.matched_count == 1
    assert res.intent_metrics.step_empty_anchor_excluded_count == 1
    assert res.intent_metrics.step_grounding_accuracy == 1.0
