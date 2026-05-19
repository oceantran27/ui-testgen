"""Tests for experiment_debug_log_service and required_input_mapping_explain."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.ui_state_extraction.schemas.evaluation_unit_schema import PredIntentUnit
from experiments.ui_state_extraction.schemas.temp_ground_truth_schema import (
    AnnotationMeta,
    ElementRecord,
    ImageMetaInTempGt,
    ScreenBlock,
    ScreenIntentRecord,
    TempGroundTruthDocument,
)
from experiments.ui_state_extraction.services.experiment_debug_log_service import (
    EXPERIMENT_PIPELINE_DEBUG_SCHEMA_VERSION,
    append_jsonl_line,
    append_module3_event,
    new_debug_log_path,
)
from experiments.ui_state_extraction.services.unit_matching_service import required_input_mapping_explain


def test_required_input_mapping_explain_dropped_ids() -> None:
    p = PredIntentUnit(
        pred_intent_index=0,
        intent_kind="submission",
        source_pred_group_id="ig",
        required_pred_element_ids=["el_a", "el_missing"],
    )
    g = ScreenIntentRecord(
        gt_intent_id="gt_intent_1",
        required_input_element_ids=["gt_el_a", "gt_el_b"],
    )
    el_m = {"el_a": "gt_el_a"}
    gt_doc = TempGroundTruthDocument(
        schema_version="t",
        annotation_meta=AnnotationMeta(source_raw_output_path="raw.json"),
        image=ImageMetaInTempGt(image_id="i", relative_path="p.png"),
        screen=ScreenBlock(),
        elements=[
            ElementRecord(gt_element_id="gt_el_a", source_model_element_id="a", anchor_texts=["a"]),
            ElementRecord(gt_element_id="gt_el_b", source_model_element_id="b", anchor_texts=["b"]),
        ],
    )
    expl = required_input_mapping_explain(p, g, el_m, gt_doc)
    assert expl["dropped_pred_ids"] == ["el_missing"]
    assert expl["mapped_gt_ids"] == ["gt_el_a"]
    assert expl["gt_required_ids"] == ["gt_el_a", "gt_el_b"]
    assert expl["required_input_f1"] is not None


def test_append_module3_writes_jsonl(tmp_path: Path) -> None:
    from experiments.ui_state_extraction.schemas.evaluation_result_schema import (
        ElementMetricsBlock,
        PerImageEvaluationResult,
    )
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
            PredElementUnit(pred_element_id="p1", anchor_texts=["x"]),
        ],
    )
    gt = TempGroundTruthDocument(
        schema_version="t",
        annotation_meta=AnnotationMeta(source_raw_output_path="raw.json"),
        image=ImageMetaInTempGt(image_id="img_x", relative_path="a.png"),
        screen=ScreenBlock(),
        elements=[
            ElementRecord(gt_element_id="gt_el_1", source_model_element_id="p1", anchor_texts=["x"]),
        ],
    )
    res = PerImageEvaluationResult(
        image_id="img_x",
        relative_path="a.png",
        element_metrics=ElementMetricsBlock(
            f1=1.0,
            text_grounded_matched_count=1,
            text_grounded_pred_count=1,
            text_grounded_gt_count=1,
        ),
    )
    log_p = new_debug_log_path(tmp_path)
    append_module3_event(
        log_p,
        pred=pred,
        gt=gt,
        per_image=res,
        group_jaccard_threshold=0.6,
        raw_output_path="raw/a.raw.json",
        temp_ground_truth_path="gt/a.temp_gt.json",
        verbose_log=False,
    )
    lines = log_p.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["schema_version"] == EXPERIMENT_PIPELINE_DEBUG_SCHEMA_VERSION
    assert row["module"] == "m3"
    assert row["intent_required_input_explain"] == []


def test_append_jsonl_line_appends(tmp_path: Path) -> None:
    p = tmp_path / "x.jsonl"
    append_jsonl_line(p, {"a": 1})
    append_jsonl_line(p, {"b": 2})
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(x) for x in lines] == [{"a": 1}, {"b": 2}]
