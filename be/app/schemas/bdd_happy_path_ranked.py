from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.bdd_happy_path import BddHappyPathResult


class VisionScenarioSummary(BaseModel):
    id: str = ""
    user_goal: str = ""
    goal_tier: str | None = None
    structural_region: str | None = None


class VisionPageOverviewSummary(BaseModel):
    functionality: str = ""
    primary_scenario_ids: list[str] | None = None


class VisionExtractionSummary(BaseModel):
    page_overview: VisionPageOverviewSummary = Field(default_factory=VisionPageOverviewSummary)
    scenarios: list[VisionScenarioSummary] = Field(default_factory=list)


class BddHappyPathRankedResponse(BaseModel):
    bdd: BddHappyPathResult
    vision_model: str = "none"
    vision: VisionExtractionSummary = Field(default_factory=VisionExtractionSummary)
