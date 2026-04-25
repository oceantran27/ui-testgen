from pydantic import BaseModel, Field


class BehaviorFlowItem(BaseModel):
    """One behavior flow: named intent and ordered screen image IDs."""

    behavior_flow: str = Field(min_length=1, max_length=200)
    screens: list[str] = Field(min_length=1)


class BehaviorFlowOrganizeResponse(BaseModel):
    """Server response: stable input_id plus clustered ordered flows (matches public JSON shape in `flows`)."""

    model: str = "gemini-2.5-flash"
    input_id: str = Field(min_length=1)
    flows: list[BehaviorFlowItem] = Field(min_length=1)
