"""Pydantic models for ui_state_extraction temp groundtruth JSON (module 2 output)."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReviewBlock(BaseModel):
    status: str = "pending"
    notes: List[str] = Field(default_factory=list)


class AnnotationMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str = "model_seeded"
    status: str = "auto_seeded"
    review_priority: str = "low"
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_notes: List[str] = Field(default_factory=list)
    source_raw_output_path: str = ""


class ImageMetaInTempGt(BaseModel):
    image_id: str
    source_path: str = ""
    relative_path: str
    filename: str = ""


class ScreenBlock(BaseModel):
    presentation_scope: str = "unknown"
    screen_type: str = "other"
    outcome_state_type: str = "neutral"
    domain: str = ""


class ElementRecord(BaseModel):
    gt_element_id: str
    source_model_element_id: str
    anchor_texts: List[str] = Field(default_factory=list)
    element_type: str = "other"
    role_hint: Optional[str] = None
    visual_region: str = "unknown"
    review: ReviewBlock = Field(default_factory=ReviewBlock)


class ActionRecord(BaseModel):
    gt_action_id: str
    source_model_action_id: str
    anchor_texts: List[str] = Field(default_factory=list)
    source_model_texts: List[str] = Field(default_factory=list)
    action_type: str = "unknown"
    action_priority: Optional[str] = None
    visual_region: str = "unknown"
    grounded_element_id: Optional[str] = None
    review: ReviewBlock = Field(default_factory=ReviewBlock)


class FeedbackRecord(BaseModel):
    gt_feedback_id: str
    source_model_feedback_id: str
    anchor_texts: List[str] = Field(default_factory=list)
    feedback_type: str = "unknown"
    visual_region: str = "unknown"
    related_element_ids: List[str] = Field(default_factory=list)
    review: ReviewBlock = Field(default_factory=ReviewBlock)


class GroupRecord(BaseModel):
    gt_group_id: str
    source_model_group_id: str
    group_type: str = "other"
    member_element_ids: List[str] = Field(default_factory=list)
    member_action_ids: List[str] = Field(default_factory=list)
    member_feedback_ids: List[str] = Field(default_factory=list)
    primary_action_id: Optional[str] = None
    review: ReviewBlock = Field(default_factory=ReviewBlock)


class ExpectedStepRecord(BaseModel):
    step_type: str
    source_action_id: Optional[str] = None
    source_element_id: Optional[str] = None


class ScreenIntentRecord(BaseModel):
    gt_intent_id: str
    source_model_index: int = 0
    intent_kind: str = ""
    source_group_id: str = ""
    primary_action_id: Optional[str] = None
    commit_action_id: Optional[str] = None
    secondary_action_ids: List[str] = Field(default_factory=list)
    required_input_element_ids: List[str] = Field(default_factory=list)
    evidence_target_ids: List[str] = Field(default_factory=list)
    expected_steps: List[ExpectedStepRecord] = Field(default_factory=list)
    review: ReviewBlock = Field(default_factory=ReviewBlock)


class UnresolvedGroupRecord(BaseModel):
    gt_unresolved_id: str
    source_model_group_id: str
    group_id: str
    reason_code: str
    review: ReviewBlock = Field(default_factory=ReviewBlock)


class InvalidReferenceRecord(BaseModel):
    field: str
    source_id: str = ""
    reason: str = ""


class ConversionReportCounts(BaseModel):
    elements: int = 0
    actions: int = 0
    feedback: int = 0
    groups: int = 0
    screen_intents: int = 0
    unresolved_groups: int = 0


class DebugIdMaps(BaseModel):
    elements: dict[str, str] = Field(default_factory=dict)
    actions: dict[str, str] = Field(default_factory=dict)
    feedback: dict[str, str] = Field(default_factory=dict)
    groups: dict[str, str] = Field(default_factory=dict)


class ConversionReport(BaseModel):
    status: str = "converted"
    warnings: List[str] = Field(default_factory=list)
    invalid_references: List[InvalidReferenceRecord] = Field(default_factory=list)
    auto_flags: List[str] = Field(default_factory=list)
    counts: ConversionReportCounts = Field(default_factory=ConversionReportCounts)
    debug_id_maps: Optional[DebugIdMaps] = None


class TempGroundTruthDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str
    annotation_meta: AnnotationMeta
    image: ImageMetaInTempGt
    screen: ScreenBlock
    elements: List[ElementRecord] = Field(default_factory=list)
    actions: List[ActionRecord] = Field(default_factory=list)
    feedback: List[FeedbackRecord] = Field(default_factory=list)
    groups: List[GroupRecord] = Field(default_factory=list)
    screen_intents: List[ScreenIntentRecord] = Field(default_factory=list)
    unresolved_groups: List[UnresolvedGroupRecord] = Field(default_factory=list)
    conversion_report: ConversionReport = Field(default_factory=ConversionReport)

    def model_dump_json_safe(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
