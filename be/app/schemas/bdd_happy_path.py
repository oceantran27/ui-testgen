from __future__ import annotations

from pydantic import BaseModel, Field


class BddFeatureBlock(BaseModel):
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
            "Business value and primary user goals for this screen; used to rank scenarios. Empty when there are no scenarios."
        ),
    )


class BddScenarioItem(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(
        min_length=1,
        description=(
            "Imperative label (2–6 words) at class level: verb + generic object; "
            "no specific product, brand, or search string (those belong in gherkin). Letter case is not prescribed."
        ),
    )
    gherkin: str = Field(min_length=1)


class BddHappyPathResult(BaseModel):
    model: str = "gemini-2.5-flash"
    feature: BddFeatureBlock
    scenarios: list[BddScenarioItem] = Field(default_factory=list)
    combined_gherkin: str = ""
