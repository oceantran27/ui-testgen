from __future__ import annotations

from pydantic import BaseModel, Field


class BddScenarioRankingLLMResponse(BaseModel):
    ordered_scenario_ids: list[str] = Field(min_length=0)
