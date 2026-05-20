"""Aggregate evaluation metrics and CSV row helpers."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class DatasetSummary(BaseModel):
    total_raw_outputs: int = 0
    total_ground_truth_files: int = 0
    total_matched_pairs: int = 0
    total_evaluated: int = 0
    total_skipped: int = 0
    skip_reasons: dict[str, int] = Field(default_factory=dict)


class AggregateMetricsV4(BaseModel):
    """Dataset-level aggregates for evaluation_summary v4 (Sprint 8).

    Screen fields are mean-per-image accuracies (three enums; domain excluded).
    Unit fields: micro uses pooled counts → PRF; macro uses mean per-image P/R/F1 with counts omitted.
    """

    presentation_scope_accuracy: Optional[float] = None
    screen_type_accuracy: Optional[float] = None
    outcome_state_type_accuracy: Optional[float] = None
    screen_enum_accuracy: Optional[float] = None

    element_precision: Optional[float] = None
    element_recall: Optional[float] = None
    element_f1: Optional[float] = None
    element_correct_count: Optional[float] = None
    element_pred_count: Optional[float] = None
    element_gt_count: Optional[float] = None

    action_precision: Optional[float] = None
    action_recall: Optional[float] = None
    action_f1: Optional[float] = None
    action_correct_count: Optional[float] = None
    action_pred_count: Optional[float] = None
    action_gt_count: Optional[float] = None

    feedback_precision: Optional[float] = None
    feedback_recall: Optional[float] = None
    feedback_f1: Optional[float] = None
    feedback_correct_count: Optional[float] = None
    feedback_pred_count: Optional[float] = None
    feedback_gt_count: Optional[float] = None

    intent_precision: Optional[float] = None
    intent_recall: Optional[float] = None
    intent_f1: Optional[float] = None
    intent_correct_count: Optional[float] = None
    intent_pred_count: Optional[float] = None
    intent_gt_count: Optional[float] = None


class DiagnosticMetrics(BaseModel):
    """Legacy pooled / auxiliary metrics (not in aggregate_metrics v4 main block)."""

    screen_enum_accuracy: Optional[float] = None

    element_precision: Optional[float] = None
    element_recall: Optional[float] = None
    element_f1: Optional[float] = None
    element_type_accuracy: Optional[float] = None
    role_hint_accuracy: Optional[float] = None
    element_region_accuracy: Optional[float] = None
    text_grounded_pred_count: Optional[float] = None
    text_grounded_gt_count: Optional[float] = None
    text_grounded_matched_count: Optional[float] = None
    pred_empty_anchor_element_count: Optional[float] = None
    gt_empty_anchor_element_count: Optional[float] = None
    empty_anchor_element_delta: Optional[float] = None
    pred_empty_anchor_element_rate: Optional[float] = None
    gt_empty_anchor_element_rate: Optional[float] = None

    action_precision: Optional[float] = None
    action_recall: Optional[float] = None
    action_f1: Optional[float] = None
    action_type_accuracy: Optional[float] = None
    action_priority_accuracy: Optional[float] = None
    action_grounding_accuracy: Optional[float] = None
    action_region_accuracy: Optional[float] = None
    action_grounding_evaluated_count: Optional[float] = None

    feedback_precision: Optional[float] = None
    feedback_recall: Optional[float] = None
    feedback_f1: Optional[float] = None
    feedback_type_accuracy: Optional[float] = None
    feedback_related_element_accuracy: Optional[float] = None
    feedback_related_empty_anchor_excluded_pred_refs: Optional[float] = None
    feedback_related_empty_anchor_excluded_gt_refs: Optional[float] = None

    group_precision: Optional[float] = None
    group_recall: Optional[float] = None
    group_f1: Optional[float] = None
    group_membership_precision: Optional[float] = None
    group_membership_recall: Optional[float] = None
    group_membership_f1: Optional[float] = None
    group_type_accuracy: Optional[float] = None
    group_primary_action_accuracy: Optional[float] = None
    group_membership_empty_anchor_excluded_pred_refs: Optional[float] = None
    group_membership_empty_anchor_excluded_gt_refs: Optional[float] = None

    intent_precision: Optional[float] = None
    intent_recall: Optional[float] = None
    intent_f1: Optional[float] = None
    intent_kind_accuracy: Optional[float] = None
    intent_source_group_accuracy: Optional[float] = None
    intent_primary_action_accuracy: Optional[float] = None
    intent_commit_action_accuracy: Optional[float] = None
    required_input_precision: Optional[float] = None
    required_input_recall: Optional[float] = None
    required_input_f1: Optional[float] = None
    required_input_correct_count: Optional[float] = None
    required_input_pred_count: Optional[float] = None
    required_input_gt_count: Optional[float] = None
    required_input_empty_anchor_excluded_gt_refs: Optional[float] = None
    required_input_empty_anchor_excluded_pred_refs: Optional[float] = None
    evidence_target_precision: Optional[float] = None
    evidence_target_recall: Optional[float] = None
    evidence_target_f1: Optional[float] = None
    evidence_target_correct_count: Optional[float] = None
    evidence_target_pred_count: Optional[float] = None
    evidence_target_gt_count: Optional[float] = None
    evidence_empty_anchor_excluded_gt_refs: Optional[float] = None
    evidence_empty_anchor_excluded_pred_refs: Optional[float] = None
    step_grounding_accuracy: Optional[float] = None
    step_precision: Optional[float] = None
    step_recall: Optional[float] = None
    step_f1: Optional[float] = None
    step_correct_count: Optional[float] = None
    step_pred_count: Optional[float] = None
    step_gt_count: Optional[float] = None
    step_empty_anchor_excluded_count: Optional[float] = None
    commit_action_accuracy: Optional[float] = None

    invalid_reference_rate: Optional[float] = None
    hallucination_rate: Optional[float] = None


# Backward-compatible alias (pre–Sprint 8 name for the diagnostic-shaped model).
AggregateMetrics = DiagnosticMetrics


class EvaluationSummaryDocument(BaseModel):
    schema_version: str
    dataset_summary: DatasetSummary = Field(default_factory=DatasetSummary)
    aggregate_metrics: AggregateMetricsV4 = Field(default_factory=AggregateMetricsV4)
    aggregate_metrics_macro: AggregateMetricsV4 = Field(default_factory=AggregateMetricsV4)
    diagnostic_metrics: Optional[DiagnosticMetrics] = None
    skipped_items: List[dict[str, Any]] = Field(default_factory=list)

    def model_dump_json_safe(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
