"""Response and internal models for the multi-image state-graph pipeline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.test_scenario_generation import FinalTestOutput


PipelinePhaseId = Literal["dedupe", "parallel_screens", "state_graph", "e2e_scenarios"]
PipelinePhaseUiStatus = Literal["pending", "running", "completed", "failed"]
RunStatus = Literal["queued", "running", "completed", "failed"]

PIPELINE_PHASE_ORDER: tuple[PipelinePhaseId, ...] = (
    "dedupe",
    "parallel_screens",
    "state_graph",
    "e2e_scenarios",
)

PIPELINE_PHASE_LABELS: dict[PipelinePhaseId, str] = {
    "dedupe": "Image deduplication",
    "parallel_screens": "UI extraction & user intents",
    "state_graph": "State graph & flows",
    "e2e_scenarios": "E2E scenarios (Actor–Critic)",
}


class PipelinePhaseTiming(BaseModel):
    """Server-measured duration for one pipeline boundary."""

    phase_id: PipelinePhaseId
    label: str
    duration_ms: int = Field(ge=0)


class PipelineRunTiming(BaseModel):
    """Full run timing from the server."""

    phases: list[PipelinePhaseTiming] = Field(min_length=0)
    wall_clock_ms: int = Field(ge=0, description="Wall time from pipeline start until completion")


class PipelinePhaseProgress(BaseModel):
    """Live or final phase row for polling UI."""

    id: PipelinePhaseId
    label: str = Field(min_length=1)
    status: PipelinePhaseUiStatus = "pending"
    started_at_iso: str | None = None
    ended_at_iso: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class StateGraphStartResponse(BaseModel):
    """Immediate response after uploads are accepted; pipeline runs in the background."""

    input_id: str = Field(min_length=1)
    status: Literal["running"] = "running"


class StateGraphInputScreen(BaseModel):
    """One screen node in the bundle sent to state-graph flow inference (prompt §2)."""

    image_id: str = Field(min_length=1)
    ui_state_type: str = Field(default="full_page", min_length=1)
    primary_heading: str = ""
    page_summary: str = ""
    navigational_destinations: list[str] = Field(default_factory=list)
    user_intents: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("user_intents", mode="before")
    @classmethod
    def _coerce_intents(cls, v: object) -> object:
        if v is None:
            return []
        return v


class StateGraphFlowItem(BaseModel):
    """One inferred user flow as an ordered list of screen node IDs (content hashes)."""

    id: str = Field(min_length=1, description="Stable flow identifier from the model or server.")
    name: str = Field(min_length=1, max_length=200, description="Human-readable flow name.")
    nodes: list[str] = Field(
        min_length=1,
        description="Ordered list of image_id (sha256 hex) nodes in this flow.",
    )


class StateGraphOrganizeResponse(BaseModel):
    """API response: flows keyed by canonical image content hashes."""

    model: str = Field(
        default="gpt-5-mini",
        description="Primary model used for flow inference (graph stage); Gemini unless id starts with gpt-.",
    )
    input_id: str = Field(min_length=1)
    flows: list[StateGraphFlowItem] = Field(min_length=1)
    final_test_output: FinalTestOutput = Field(
        default_factory=FinalTestOutput,
        description=(
            "Per-screen isolated Gherkin (from user intents) and E2E flow scenarios "
            "(Actor–Critic, stage 4)."
        ),
    )
    pipeline_timing: PipelineRunTiming | None = Field(
        default=None,
        description="Measured phase and wall-clock timings when pipeline finished successfully.",
    )
    screen_images: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Maps canonical image_id (sha256 hex) to uploaded filename basename under "
            "`uploads/state-graph-input/{input_id}/` for static URLs."
        ),
    )


class StateGraphRunStatusResponse(BaseModel):
    """Poll payload for `/state-graph/status/{input_id}`."""

    input_id: str = Field(min_length=1)
    status: RunStatus
    current_phase: PipelinePhaseId | None = None
    phases: list[PipelinePhaseProgress] = Field(default_factory=list)
    error: str | None = None
    result: StateGraphOrganizeResponse | None = None
    timing: PipelineRunTiming | None = None


class UserIntentEvidenceItem(BaseModel):
    """One user intent plus control ids from ui-flat-v5 extraction (`controls[].id`)."""

    intent: str = Field(
        min_length=1,
        description=(
            "Generalized English imperative (e.g. 'Search for records'); no 'by'/'using', "
            "no verbatim UI labels or quotes in this field (see isolated scenarios prompt)."
        ),
    )
    gherkin: str = Field(default="", description="BDD/Gherkin scenario corresponding to this intent.")
    control_ids: list[str] = Field(
        min_length=1,
        description="Non-empty list of control ids; each must exist in the input controls list.",
    )

    @field_validator("control_ids")
    @classmethod
    def control_ids_unique_and_non_empty(cls, v: list[str]) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError("control_ids must not contain duplicates")
        for x in v:
            if not isinstance(x, str) or not x.strip():
                raise ValueError("each control_ids entry must be a non-empty string")
        return v


class UserIntentPerImage(BaseModel):
    """Per-screen user intents with evidence control ids derived from UI extraction JSON."""

    image_id: str = Field(min_length=1)
    user_intents: list[UserIntentEvidenceItem] = Field(default_factory=list)
