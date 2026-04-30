from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

BddScenarioPriority = Literal["primary", "secondary", "utility"]
# Backward-compatible alias for imports
BddScenarioTier = BddScenarioPriority


class BddFeatureBlock(BaseModel):
    name: str = Field(
        min_length=1,
        description=(
            "Short generic page/screen label (2–8 words), no product or brand instance names; letter case is not prescribed."
        ),
    )
    description: str = ""


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
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence for Then-clause predictions only (0-1).")
    priority: BddScenarioPriority = Field(
        description=(
            "Layout-based order hint: primary = core action in main body; "
            "secondary = supporting actions in main body; utility = global chrome (header/footer/app shell)."
        ),
        validation_alias=AliasChoices("priority", "tier"),
    )


class BddHappyPathResult(BaseModel):
    model: str = "gemini-2.5-flash"
    feature: BddFeatureBlock
    scenarios: list[BddScenarioItem] = Field(default_factory=list)
    combined_gherkin: str = ""
