"""Shared Pydantic building blocks for flow_discovery experiments (DB-free)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReviewInfo(BaseModel):
    """Human review attachment for Ground Truth artefacts."""

    model_config = ConfigDict(extra="ignore")

    review_status: str = "unreviewed"
    review_notes: str = ""
    edited_fields: List[str] = Field(default_factory=list)


class ProposalMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    proposal_source: str = ""
    proposal_flow_id: Optional[str] = None
    proposal_confidence: Optional[str] = None


class ValidationWarning(BaseModel):
    """Structured warning emitted by draft auto-validation (Sprint 4)."""

    model_config = ConfigDict(extra="ignore")

    warning_code: str
    message: str


class AutoValidationBlock(BaseModel):
    """Filled by Sprint 4 auto-validation; stores flags/warnings/extra probes."""

    model_config = ConfigDict(extra="ignore")

    warnings: List[str] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    extras: Dict[str, Any] = Field(default_factory=dict)
