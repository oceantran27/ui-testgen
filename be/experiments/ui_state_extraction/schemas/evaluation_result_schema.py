"""Per-image and skipped-item results for module 3."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class SkipItem(BaseModel):
    image_id: str = ""
    relative_path: str = ""
    reason: str


class ScreenMetricsBlock(BaseModel):
    total_fields: int = 0
    correct_fields: int = 0
    accuracy: Optional[float] = None


class ElementMetricsBlock(BaseModel):
    """Element P/R/F1 are text-grounded only (normalize_text_list(anchors) non-empty)."""

    gt_count: int = 0
    pred_count: int = 0
    matched_count: int = 0  # text-grounded successful matches (same as text_grounded_matched_count)
    text_grounded_pred_count: int = 0
    text_grounded_gt_count: int = 0
    text_grounded_matched_count: int = 0
    pred_empty_anchor_element_count: int = 0
    gt_empty_anchor_element_count: int = 0
    empty_anchor_element_delta: int = 0
    pred_empty_anchor_element_rate: Optional[float] = None
    gt_empty_anchor_element_rate: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    element_type_accuracy: Optional[float] = None
    role_hint_accuracy: Optional[float] = None
    visual_region_accuracy: Optional[float] = None


class ActionMetricsBlock(BaseModel):
    gt_count: int = 0
    pred_count: int = 0
    matched_count: int = 0
    action_grounding_evaluated_count: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    action_type_accuracy: Optional[float] = None
    action_priority_accuracy: Optional[float] = None
    action_region_accuracy: Optional[float] = None
    action_grounding_accuracy: Optional[float] = None


class FeedbackMetricsBlock(BaseModel):
    gt_count: int = 0
    pred_count: int = 0
    matched_count: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    feedback_type_accuracy: Optional[float] = None
    feedback_related_element_accuracy: Optional[float] = None
    feedback_related_empty_anchor_excluded_pred_refs: int = 0
    feedback_related_empty_anchor_excluded_gt_refs: int = 0


class GroupMetricsBlock(BaseModel):
    gt_count: int = 0
    pred_count: int = 0
    matched_count: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    group_membership_precision: Optional[float] = None
    group_membership_recall: Optional[float] = None
    group_membership_f1: Optional[float] = None
    group_type_accuracy: Optional[float] = None
    primary_action_accuracy: Optional[float] = None
    group_membership_empty_anchor_excluded_pred_refs: int = 0
    group_membership_empty_anchor_excluded_gt_refs: int = 0


class IntentMetricsBlock(BaseModel):
    gt_count: int = 0
    pred_count: int = 0
    matched_count: int = 0
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    intent_kind_accuracy: Optional[float] = None
    intent_source_group_accuracy: Optional[float] = None
    intent_primary_action_accuracy: Optional[float] = None
    intent_commit_action_accuracy: Optional[float] = None
    required_input_precision: Optional[float] = None
    required_input_recall: Optional[float] = None
    required_input_f1: Optional[float] = None
    required_input_empty_anchor_excluded_gt_refs: int = 0
    required_input_empty_anchor_excluded_pred_refs: int = 0
    evidence_target_precision: Optional[float] = None
    evidence_target_recall: Optional[float] = None
    evidence_target_f1: Optional[float] = None
    evidence_empty_anchor_excluded_gt_refs: int = 0
    evidence_empty_anchor_excluded_pred_refs: int = 0
    step_grounding_accuracy: Optional[float] = None
    step_empty_anchor_excluded_count: int = 0


class ConsistencyMetricsBlock(BaseModel):
    invalid_reference_count: int = 0
    total_references_checked: int = 0
    invalid_reference_rate: Optional[float] = None
    # Text-grounded pred elements with no GT match (empty-anchor preds excluded; see ElementMetricsBlock).
    hallucinated_element_count: int = 0
    hallucinated_action_count: int = 0
    hallucinated_feedback_count: int = 0
    hallucinated_group_count: int = 0
    hallucinated_intent_count: int = 0
    hallucinated_unit_count: int = 0
    total_pred_units: int = 0
    hallucination_rate: Optional[float] = None


class PerImageEvaluationResult(BaseModel):
    image_id: str
    relative_path: str
    status: str = "evaluated"

    screen_metrics: ScreenMetricsBlock = Field(default_factory=ScreenMetricsBlock)
    element_metrics: ElementMetricsBlock = Field(default_factory=ElementMetricsBlock)
    action_metrics: ActionMetricsBlock = Field(default_factory=ActionMetricsBlock)
    feedback_metrics: FeedbackMetricsBlock = Field(default_factory=FeedbackMetricsBlock)
    group_metrics: GroupMetricsBlock = Field(default_factory=GroupMetricsBlock)
    intent_metrics: IntentMetricsBlock = Field(default_factory=IntentMetricsBlock)
    consistency_metrics: ConsistencyMetricsBlock = Field(default_factory=ConsistencyMetricsBlock)

    debug: dict[str, Any] = Field(default_factory=dict)

    def model_dump_json_safe(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
