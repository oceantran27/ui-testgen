from pydantic import BaseModel, Field


class BddFeatureBlock(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


class BddScenarioItem(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    gherkin: str = Field(min_length=1)


class BddHappyPathResult(BaseModel):
    model: str = "gemini-2.5-flash"
    feature: BddFeatureBlock
    scenarios: list[BddScenarioItem] = Field(min_length=1)
    combined_gherkin: str = ""
