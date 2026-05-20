"""Sprint 10: slim per-image CSV and structured Markdown report."""

from __future__ import annotations

from pathlib import Path

from experiments.ui_state_extraction.schemas.evaluation_metric_schema import DatasetSummary
from experiments.ui_state_extraction.schemas.experiment_raw_output_schema import (
    ExperimentRawOutputDocument,
    ImageMetaInRawOutput,
    ModelCallMeta,
)
from experiments.ui_state_extraction.services.evaluation_report_service import (
    SPRINT10_PER_IMAGE_CSV_HEADER,
    per_image_csv_rows,
    write_markdown_report,
)
from experiments.ui_state_extraction.services.metric_calculation_service import (
    aggregate_dataset_metrics_v4,
    evaluate_pair,
)
from experiments.ui_state_extraction.services.prediction_normalizer_service import (
    normalize_raw_model_output,
)
from experiments.ui_state_extraction.services.temp_ground_truth_builder_service import (
    build_temp_ground_truth_from_raw,
)

from tests.unit.test_ui_state_extraction_module2 import _login_raw_payload


def test_sprint10_per_image_csv_exact_columns_and_login_row() -> None:
    raw = _login_raw_payload()
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="exp_auth_login_login_empty",
            relative_path="auth/login/login_empty.png",
            filename="login_empty.png",
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
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    rows = per_image_csv_rows([res])
    assert rows[0] == SPRINT10_PER_IMAGE_CSV_HEADER
    assert len(rows[0]) == 33
    row = dict(zip(rows[0], rows[1], strict=True))
    assert row["image_id"] == res.image_id
    assert row["screen_enum_accuracy"] == res.screen_metrics.accuracy
    assert row["element_correct_count"] == res.element_metrics.text_grounded_matched_count
    assert row["skipped_empty_key_element_count"] == res.key_diagnostics.skipped_empty_key_element_count


def test_sprint10_csv_reports_skipped_feedback_on_key_metrics_path() -> None:
    raw = _login_raw_payload()
    raw["ui_state"]["visible_feedback"] = [
        {"feedback_id": "fb_bad", "feedback_type": "error", "text": []},
    ]
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="exp_auth_login_login_empty",
            relative_path="auth/login/login_empty.png",
            filename="login_empty.png",
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
        include_debug=False,
        use_key_counters=True,
    )
    row = dict(zip(SPRINT10_PER_IMAGE_CSV_HEADER, per_image_csv_rows([res])[1], strict=True))
    assert int(row["skipped_empty_key_feedback_count"]) >= 1


def test_sprint10_markdown_eight_sections_without_legacy_metric_tokens(tmp_path: Path) -> None:
    raw = _login_raw_payload()
    doc = ExperimentRawOutputDocument(
        schema_version="experiment_raw_output_v1",
        experiment_name="ui_state_extraction",
        image=ImageMetaInRawOutput(
            image_id="exp_auth_login_login_empty",
            relative_path="auth/login/login_empty.png",
            filename="login_empty.png",
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
    res = evaluate_pair(pred, gt, raw, group_jaccard_threshold=0.6, include_debug=False)
    micro, macro, _diag = aggregate_dataset_metrics_v4([res])
    ds = DatasetSummary(
        total_raw_outputs=1,
        total_ground_truth_files=1,
        total_matched_pairs=1,
        total_evaluated=1,
        total_skipped=0,
        skip_reasons={"none": 0},
    )
    path = tmp_path / "evaluation_report.md"
    write_markdown_report(path, dataset_summary=ds, micro=micro, macro=macro, results=[res])
    body = path.read_text(encoding="utf-8")
    for heading in (
        "## 1. Dataset summary",
        "## 2. Screen classification results",
        "## 3. Element extraction results",
        "## 4. Action extraction results",
        "## 5. Feedback extraction results",
        "## 6. Intent inference results",
        "## 7. Diagnostics: skipped/missing keys",
        "## 8. Notes and limitations",
    ):
        assert heading in body
    assert "group_f1" not in body
    assert "step_f1" not in body
    assert "hallucination_rate" not in body
