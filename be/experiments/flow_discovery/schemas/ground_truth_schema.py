"""
Ground-truth package v2 for behavioural flow discovery (review + evaluation).

Converters populate stable ``gt_*`` ids; catalogue ``state_id`` is stored as
``catalog_state_id``. ``semantic_flow_kind`` classifies behavioural intent of a
composed flow separately from production ``flow_type``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from experiments.flow_discovery import config
from experiments.flow_discovery.io_utils import utc_now_iso
from experiments.flow_discovery.schemas.common_schema import AutoValidationBlock, ProposalMeta, ReviewInfo


class VisibleEvidenceBuckets(BaseModel):
    model_config = ConfigDict(extra="ignore")

    headings: List[str] = Field(default_factory=list)
    texts: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    feedback: List[str] = Field(default_factory=list)


class GroundTruthState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gt_state_id: str
    catalog_state_id: str
    source_image_id: str = ""
    screen_name: str = ""
    screen_type: str = ""
    outcome_state_type: str = ""
    taxonomy: Dict[str, Any] = Field(default_factory=dict)
    visible_evidence: VisibleEvidenceBuckets = Field(default_factory=VisibleEvidenceBuckets)
    review: ReviewInfo = Field(default_factory=ReviewInfo)


class GroundTruthAction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gt_action_id: str
    system_action_id: str = ""
    source_state_gt_id: str
    action_text: str = ""
    action_type: str = ""
    intent_id: Optional[str] = None
    secondary_texts: List[str] = Field(default_factory=list)
    review: ReviewInfo = Field(default_factory=ReviewInfo)


class GroundTruthTransition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gt_transition_id: str

    from_state_id: str
    to_state_id: str

    trigger_action_id: Optional[str] = None
    trigger_action_text: str

    outcome_type: str
    required_input_condition: Optional[str] = None
    expected_visible_evidence: List[str] = Field(default_factory=list)

    proposal_source: str
    proposal_flow_id: Optional[str] = None
    proposal_confidence: Optional[str] = None

    auto_validation: Dict[str, Any] = Field(default_factory=dict)
    review: ReviewInfo = Field(default_factory=ReviewInfo)

    eval_include: bool = True


class GroundTruthFlow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gt_flow_id: str
    source_flow_id: Optional[str] = None

    flow_type: str = ""
    semantic_flow_kind: str = ""
    flow_name: str = ""
    ordered_state_ids: List[str] = Field(default_factory=list)
    entry_state_id: str = ""
    terminal_state_id: str = ""
    transition_ids: List[str] = Field(default_factory=list)

    proposal: ProposalMeta = Field(default_factory=ProposalMeta)
    review: ReviewInfo = Field(default_factory=ReviewInfo)
    eval_include: bool = True


class GroundTruthBranchGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    branch_group_id: str
    anchor_source_gt_state_id: str = ""
    normalized_trigger: str = ""
    state_ids: List[str] = Field(default_factory=list)
    branching_flow_id: Optional[str] = None
    alternative_transition_ids: List[str] = Field(default_factory=list)
    rationale: str = ""

    proposal: ProposalMeta = Field(default_factory=ProposalMeta)
    review: ReviewInfo = Field(default_factory=ReviewInfo)
    eval_include: bool = True


class GroundTruthFlowPackage(BaseModel):
    schema_version: str = Field(default=config.GROUND_TRUTH_SCHEMA_VERSION)

    app_id: str
    source_raw_run_id: Optional[str] = None

    states: List[GroundTruthState] = Field(default_factory=list)
    actions: List[GroundTruthAction] = Field(default_factory=list)
    transitions: List[GroundTruthTransition] = Field(default_factory=list)
    flows: List[GroundTruthFlow] = Field(default_factory=list)
    branch_groups: List[GroundTruthBranchGroup] = Field(default_factory=list)

    package_review: ReviewInfo = Field(default_factory=ReviewInfo)
    package_auto_validation: AutoValidationBlock = Field(default_factory=AutoValidationBlock)

    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: Optional[str] = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("schema_version")
    @classmethod
    def _schema_matches_package(cls, v: str) -> str:
        if v != config.GROUND_TRUTH_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {config.GROUND_TRUTH_SCHEMA_VERSION!r}, got {v!r}",
            )
        return v

    @field_validator("app_id")
    @classmethod
    def _non_empty_app_id(cls, v: str) -> str:
        stripped = str(v).strip()
        if not stripped:
            raise ValueError("app_id must be non-empty")
        return stripped
