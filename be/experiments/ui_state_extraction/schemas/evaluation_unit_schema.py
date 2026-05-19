"""Normalized prediction units for module 3 evaluation."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class PredScreenUnit(BaseModel):
    presentation_scope: str = "unknown"
    screen_type: str = "other"
    outcome_state_type: str = "neutral"
    domain: str = ""


class PredElementUnit(BaseModel):
    pred_element_id: str
    anchor_texts: List[str] = Field(default_factory=list)
    element_type: str = "other"
    role_hint: Optional[str] = None
    visual_region: str = "unknown"


class PredActionUnit(BaseModel):
    pred_action_id: str
    source_model_texts: List[str] = Field(default_factory=list)
    anchor_texts: List[str] = Field(default_factory=list)
    action_type: str = "unknown"
    action_priority: Optional[str] = None
    visual_region: str = "unknown"
    grounded_pred_element_id: Optional[str] = None


class PredFeedbackUnit(BaseModel):
    pred_feedback_id: str
    anchor_texts: List[str] = Field(default_factory=list)
    feedback_type: str = "unknown"
    visual_region: str = "unknown"
    related_pred_element_ids: List[str] = Field(default_factory=list)


class PredGroupUnit(BaseModel):
    pred_group_id: str
    group_type: str = "other"
    member_pred_element_ids: List[str] = Field(default_factory=list)
    member_pred_action_ids: List[str] = Field(default_factory=list)
    member_pred_feedback_ids: List[str] = Field(default_factory=list)
    primary_pred_action_id: Optional[str] = None


class PredExpectedStepUnit(BaseModel):
    step_type: str
    source_pred_action_id: Optional[str] = None
    source_pred_element_id: Optional[str] = None


class PredIntentUnit(BaseModel):
    pred_intent_index: int
    intent_kind: str = ""
    source_pred_group_id: str = ""
    primary_pred_action_id: Optional[str] = None
    commit_pred_action_id: Optional[str] = None
    secondary_pred_action_ids: List[str] = Field(default_factory=list)
    required_pred_element_ids: List[str] = Field(default_factory=list)
    evidence_pred_target_ids: List[str] = Field(default_factory=list)
    expected_steps: List[PredExpectedStepUnit] = Field(default_factory=list)


class PredictionEvaluationBundle(BaseModel):
    """Normalized prediction side for one image."""

    screen: PredScreenUnit
    elements: List[PredElementUnit] = Field(default_factory=list)
    actions: List[PredActionUnit] = Field(default_factory=list)
    feedback: List[PredFeedbackUnit] = Field(default_factory=list)
    groups: List[PredGroupUnit] = Field(default_factory=list)
    intents: List[PredIntentUnit] = Field(default_factory=list)
    auto_flags: List[str] = Field(default_factory=list)

    def model_dump_json_safe(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
