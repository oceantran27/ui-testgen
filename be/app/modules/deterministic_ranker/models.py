from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.modules.evaluator_rationalizer.models import ScenarioEvaluationScores


class Module2ScenarioInput(BaseModel):
    scenario_id: str
    user_goal: str
    rationale: str
    scores: ScenarioEvaluationScores


class RankedScenarioOutput(Module2ScenarioInput):
    final_score: float = Field(ge=0.0, le=10.0)
    rank_position: int = Field(ge=1)


class RankerMetadata(BaseModel):
    module_name: str = "module_3_deterministic_ranker"
    algorithm: str = "weighted_sum_model"
    version: str
    weights: dict[str, float]
    used_pandas: bool
    ranked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RankerResult(BaseModel):
    metadata: RankerMetadata
    ranked_scenarios: list[RankedScenarioOutput] = Field(default_factory=list)
