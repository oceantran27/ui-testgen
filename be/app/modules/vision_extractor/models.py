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

GoalTier = Literal["primary", "enabling", "secondary", "utility"]

StructuralRegion = Literal[
    "main",
    "form",
    "header",
    "nav",
    "sidebar",
    "footer",
    "modal",
    "toast",
    "unknown",
]


class InteractionFootprint(BaseModel):
    approx_step_count: int = Field(ge=1, le=10, description="Minimal user steps for happy path from current view")
    uses_multi_field_form: bool = False


class PageOverview(BaseModel):
    functionality: str
    target_users: str
    business_rules: list[str] = Field(default_factory=list)
    primary_scenario_ids: list[str] | None = None


class ScenarioSpec(BaseModel):
    id: str
    user_goal: str
    category: ScenarioCategory
    actor: ScenarioActor
    expected_outcome: str
    goal_tier: GoalTier | None = None
    structural_region: StructuralRegion | None = None
    interaction_footprint: InteractionFootprint | None = None
    evidence_literals: list[str] = Field(default_factory=list)


class VisionExtractionPayload(BaseModel):
    page_overview: PageOverview
    scenarios: list[ScenarioSpec] = Field(default_factory=list)


class VisionExtractionResult(BaseModel):
    module_name: str = "module_1_vision_extractor"
    model: str
    raw_output: str
    normalized_output: str
    extraction_payload: VisionExtractionPayload
