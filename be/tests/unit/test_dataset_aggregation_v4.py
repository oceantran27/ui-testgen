"""Sprint 8: dataset-level aggregate_dataset_metrics_v4 (+ diagnostic legacy split)."""

from __future__ import annotations

from experiments.ui_state_extraction.schemas.evaluation_result_schema import (
    ActionMetricsBlock,
    ElementMetricsBlock,
    FeedbackMetricsBlock,
    GroupMetricsBlock,
    IntentMetricsBlock,
    PerImageEvaluationResult,
    ScreenMetricsBlock,
)
from experiments.ui_state_extraction.services.metric_calculation_service import aggregate_dataset_metrics_v4


def _minimal_result(
    *,
    image_id: str,
    screen: ScreenMetricsBlock,
    element: ElementMetricsBlock,
    action: ActionMetricsBlock,
    feedback: FeedbackMetricsBlock,
    intent: IntentMetricsBlock,
) -> PerImageEvaluationResult:
    return PerImageEvaluationResult(
        image_id=image_id,
        relative_path=f"{image_id}.png",
        screen_metrics=screen,
        element_metrics=element,
        action_metrics=action,
        feedback_metrics=feedback,
        group_metrics=GroupMetricsBlock(),
        intent_metrics=intent,
    )


def test_aggregate_v4_screen_mean_and_enum_average() -> None:
    a = _minimal_result(
        image_id="a",
        screen=ScreenMetricsBlock(
            presentation_scope_match=True,
            screen_type_match=True,
            outcome_state_type_match=False,
        ),
        element=ElementMetricsBlock(
            text_grounded_matched_count=1,
            text_grounded_pred_count=1,
            text_grounded_gt_count=1,
            matched_count=1,
            pred_count=1,
            gt_count=1,
            precision=1.0,
            recall=1.0,
            f1=1.0,
        ),
        action=ActionMetricsBlock(matched_count=0, pred_count=0, gt_count=0),
        feedback=FeedbackMetricsBlock(matched_count=0, pred_count=0, gt_count=0),
        intent=IntentMetricsBlock(matched_count=0, pred_count=0, gt_count=0),
    )
    b = _minimal_result(
        image_id="b",
        screen=ScreenMetricsBlock(
            presentation_scope_match=False,
            screen_type_match=True,
            outcome_state_type_match=True,
        ),
        element=ElementMetricsBlock(
            text_grounded_matched_count=0,
            text_grounded_pred_count=1,
            text_grounded_gt_count=1,
            matched_count=0,
            pred_count=1,
            gt_count=1,
            precision=0.0,
            recall=0.0,
            f1=0.0,
        ),
        action=ActionMetricsBlock(matched_count=0, pred_count=0, gt_count=0),
        feedback=FeedbackMetricsBlock(matched_count=0, pred_count=0, gt_count=0),
        intent=IntentMetricsBlock(matched_count=0, pred_count=0, gt_count=0),
    )

    micro, macro, diagnostic = aggregate_dataset_metrics_v4([a, b])

    assert micro["presentation_scope_accuracy"] == 0.5
    assert micro["screen_type_accuracy"] == 1.0
    assert micro["outcome_state_type_accuracy"] == 0.5
    assert micro["screen_enum_accuracy"] == (0.5 + 1.0 + 0.5) / 3

    assert micro["element_correct_count"] == 1.0
    assert micro["element_pred_count"] == 2.0
    assert micro["element_gt_count"] == 2.0
    assert micro["element_precision"] == 0.5
    assert micro["element_recall"] == 0.5
    assert micro["element_f1"] == 0.5

    assert macro["element_f1"] == 0.5
    assert macro.get("element_correct_count") is None

    assert "group_f1" not in micro
    assert diagnostic.group_f1 is None


def test_aggregate_v4_empty_results() -> None:
    micro, macro, diagnostic = aggregate_dataset_metrics_v4([])
    assert micro == {}
    assert macro == {}
    assert diagnostic.model_dump(mode="json", exclude_none=True) == {}
