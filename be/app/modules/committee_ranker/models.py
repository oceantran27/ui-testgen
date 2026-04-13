from datetime import datetime, timezone
from typing import Iterable

from pydantic import BaseModel, Field


class CommitteeScenarioInput(BaseModel):
    scenario_id: str
    user_goal: str
    conflict_resolution_summary: str
    BA_score: int = Field(ge=1, le=10)
    QA_score: int = Field(ge=1, le=10)
    UX_score: int = Field(ge=1, le=10)


class RankedCommitteeScenarioOutput(CommitteeScenarioInput):
    final_score: float = Field(ge=0.0, le=10.0)
    rank_position: int = Field(ge=1)


class CommitteeRankerMetadata(BaseModel):
    module_name: str = "module_4_committee_ranker"
    algorithm: str = "weighted_sum_committee_model"
    version: str
    weights: dict[str, float]
    ranked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CommitteeRankerResult(BaseModel):
    metadata: CommitteeRankerMetadata
    ranked_scenarios: list[RankedCommitteeScenarioOutput] = Field(default_factory=list)
