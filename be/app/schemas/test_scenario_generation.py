from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ScreenFeatureSummary(BaseModel):
    name: str = Field(
        min_length=1,
        description=(
            "Short generic page/screen label (2–8 words), no product or brand instance names; letter case is not prescribed."
        ),
    )
    description: str = ""
    business_intent: str = Field(
        default="",
        description=(
            "Business value and primary user goals for this screen. Empty when there are no scenarios."
        ),
    )


class TestScenarioItem(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(
        min_length=1,
        description=(
            "Imperative label (2–6 words) at class level: verb + generic object; "
            "no specific product, brand, or search string (those belong in test_scenario). Letter case is not prescribed."
        ),
    )
    test_scenario: str = Field(min_length=1)

    @field_validator("test_scenario", mode="before")
    @classmethod
    def join_test_scenario_if_list(cls, v: str | list[str]) -> str:
        if isinstance(v, list):
            return "\n".join(v)
        return v


class TestScenarioSuite(BaseModel):
    model: str = "gemini-2.5-flash"
    feature: ScreenFeatureSummary
    scenarios: list[TestScenarioItem] = Field(default_factory=list)
    combined_test_scenario: str = ""
