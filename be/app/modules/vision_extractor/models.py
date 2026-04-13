from typing import Literal

from pydantic import BaseModel, Field

ScenarioCategory = Literal[
    "authentication",
    "navigation",
    "data_entry",
    "data_retrieval",
    "filtering",
    "search",
    "export",
    "payment",
    "notification",
    "settings",
    "bulk_action",
    "other",
]

ScenarioActor = Literal[
    "end_user",
    "guest",
    "authenticated_user",
    "admin",
    "agent",
    "merchant",
    "customer",
    "moderator",
    "analyst",
    "other",
]


class PageOverview(BaseModel):
    functionality: str
    target_users: str
    business_rules: list[str] = Field(default_factory=list)


class ScenarioEvaluationScores(BaseModel):
    core_alignment: int = Field(ge=1, le=10)
    frequency: int = Field(ge=1, le=10)
    business_risk: int = Field(ge=1, le=10)


class ScenarioEvaluation(BaseModel):
    rationale: str = Field(min_length=1)
    scores: ScenarioEvaluationScores


class ScenarioSpec(BaseModel):
    id: str
    user_goal: str
    category: ScenarioCategory
    actor: ScenarioActor
    expected_outcome: str
    evaluation: ScenarioEvaluation | None = None


class VisionExtractionPayload(BaseModel):
    page_overview: PageOverview
    scenarios: list[ScenarioSpec] = Field(default_factory=list)


class VisionExtractionResult(BaseModel):
    module_name: str = "module_1_vision_extractor"
    model: str
    raw_output: str
    normalized_output: str
    extraction_payload: VisionExtractionPayload
