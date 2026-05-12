from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any, Dict
from datetime import datetime


# ──────────────────────────────────────────────
# Run Config schema
# ──────────────────────────────────────────────

class RunConfig(BaseModel):
    """Per-run configuration. All fields have sensible defaults."""

    model_config = ConfigDict(extra="ignore")

    allow_unordered_images: bool = Field(default=True, description="Allow images without ordering")
    allow_duplicate_images: bool = Field(default=True, description="Allow duplicate images in input")
    input_level_mode: str = Field(default="auto_detect", description="Level detection mode")
    max_revision_round: int = Field(default=2, description="Max Actor-Critic revision rounds")


# ──────────────────────────────────────────────
# Request schemas
# ──────────────────────────────────────────────

class RunCreateRequest(BaseModel):
    """Body for POST /runs"""
    project_name: Optional[str] = Field(default=None, description="Human-readable project name")
    description: Optional[str] = Field(default=None, description="Optional run description")
    config: Optional[RunConfig] = Field(default=None, description="Run configuration overrides")


# ──────────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────────

class RunResponse(BaseModel):
    """Standard run representation returned to clients."""
    run_id: str
    project_name: Optional[str] = None
    description: Optional[str] = None
    status: str
    total_images: int = 0
    valid_images: int = 0
    invalid_images: int = 0
    canonical_images: int = 0
    duplicate_groups_count: int = 0
    config: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    # LangGraph tracking (also on GET /runs/{id}/graph-status — duplicated here so one poll suffices)
    current_phase: Optional[str] = None
    current_node: Optional[str] = None
    progress_percentage: Optional[int] = None
    graph_status: Optional[str] = None

    model_config = {"from_attributes": True}


class RunSubmitResponse(BaseModel):
    """Response for POST /runs/{run_id}/submit"""
    run_id: str
    status: str
    job_id: Optional[str] = None
    message: str


class RunCancelResponse(BaseModel):
    """Response for POST /runs/{run_id}/cancel"""
    run_id: str
    status: str
    message: str


class RunListResponse(BaseModel):
    """Response for GET /runs"""
    runs: List[RunResponse]
    total: int


class PipelineLogResponse(BaseModel):
    """Latest pipeline.log from worker session dir for this run (if any)."""

    run_id: str
    content: Optional[str] = None
    path: Optional[str] = None
    message: Optional[str] = None
    next_byte: int = Field(
        default=0,
        description="Byte offset after this response; pass as from_byte on the next incremental request.",
    )
