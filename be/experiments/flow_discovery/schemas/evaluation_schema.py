"""Evaluation outcome schema for raw/repaired predictions vs reviewed ground truth (Sprint 5)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from experiments.flow_discovery import config
from experiments.flow_discovery.io_utils import utc_now_iso


class TransitionMatchItem(BaseModel):
    """Per-predicted-transition match verdict (TP/FP) or false-negative row."""

    pred_transition_id: Optional[str] = None
    gt_transition_id: Optional[str] = None

    match_status: str = "unknown"
    matched_gt_transition_id: Optional[str] = None
    match_mode: Optional[str] = None

    error_tags: List[str] = Field(default_factory=list)
    notes: str = ""

    model_config = ConfigDict(extra="ignore")


class FlowEvalItem(BaseModel):
    gt_flow_id: Optional[str] = None
    pred_flow_id: Optional[str] = None
    match_status: str = "unknown"
    member_transition_hits: int = 0
    member_transition_misses: int = 0
    ordering_errors: int = 0
    ordering_accuracy: Optional[float] = None
    membership_f1: Optional[float] = None
    error_tags: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class BranchEvalItem(BaseModel):
    branch_key: str = ""
    gt_branch_group_id: Optional[str] = None
    pred_semantic_cluster_id: Optional[str] = None
    match_status: str = "unknown"
    error_tags: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class TransitionMetrics(BaseModel):
    strict_precision: Optional[float] = None
    strict_recall: Optional[float] = None
    strict_f1: Optional[float] = None
    relaxed_precision: Optional[float] = None
    relaxed_recall: Optional[float] = None
    relaxed_f1: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


class FlowMetrics(BaseModel):
    membership_macro_f1: Optional[float] = None
    ordering_accuracy: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


class BranchMetrics(BaseModel):
    branch_precision: Optional[float] = None
    branch_recall: Optional[float] = None
    branch_f1: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


class ErrorMetrics(BaseModel):
    invalid_transition_count: int = 0
    invalid_flow_rate: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


class EvaluationMetricsNested(BaseModel):
    transition_metrics: TransitionMetrics = Field(default_factory=TransitionMetrics)
    flow_metrics: FlowMetrics = Field(default_factory=FlowMetrics)
    branch_metrics: BranchMetrics = Field(default_factory=BranchMetrics)
    error_metrics: ErrorMetrics = Field(default_factory=ErrorMetrics)

    model_config = ConfigDict(extra="ignore")


class EvaluationResult(BaseModel):
    schema_version: str = Field(default=config.EVALUATION_SCHEMA_VERSION)

    app_id: str
    run_id: Optional[str] = None

    metrics: EvaluationMetricsNested = Field(default_factory=EvaluationMetricsNested)
    transition_items: List[TransitionMatchItem] = Field(default_factory=list)
    flow_items: List[FlowEvalItem] = Field(default_factory=list)
    branch_items: List[BranchEvalItem] = Field(default_factory=list)

    error_breakdown: Dict[str, int] = Field(default_factory=dict)
    extras: Dict[str, Any] = Field(default_factory=dict)

    created_at: str = Field(default_factory=utc_now_iso)

    model_config = ConfigDict(extra="ignore")

    @field_validator("schema_version")
    @classmethod
    def _schema_matches(cls, v: str) -> str:
        if v != config.EVALUATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {config.EVALUATION_SCHEMA_VERSION!r}, got {v!r}",
            )
        return v

    @field_validator("app_id")
    @classmethod
    def _non_empty_app_id(cls, v: str) -> str:
        stripped = str(v).strip()
        if not stripped:
            raise ValueError("app_id must be non-empty")
        return stripped


TransitionEvalItem = TransitionMatchItem
EvaluationMetrics = EvaluationMetricsNested

__all__ = [
    "BranchEvalItem",
    "BranchMetrics",
    "ErrorMetrics",
    "EvaluationMetrics",
    "EvaluationMetricsNested",
    "EvaluationResult",
    "FlowEvalItem",
    "FlowMetrics",
    "TransitionEvalItem",
    "TransitionMatchItem",
    "TransitionMetrics",
]
