"""Response and internal models for the multi-image state-graph pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.test_scenario_generation import FinalTestOutput


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


class UserIntentEvidenceItem(BaseModel):
    """One user intent plus control ids from ui-flat-v5 extraction (`controls[].id`)."""

    intent: str = Field(min_length=1, description="English intent phrase for this screen.")
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
