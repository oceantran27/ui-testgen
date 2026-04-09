from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScenarioEvaluationScores(BaseModel):
    core_alignment: int = Field(ge=1, le=10)
    frequency: int = Field(ge=1, le=10)
    business_risk: int = Field(ge=1, le=10)


class ScenarioEvaluation(BaseModel):
    rationale: str = Field(min_length=1)
    scores: ScenarioEvaluationScores


class ScenarioEvaluationPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    evaluation: ScenarioEvaluation


class EvaluatorPatchedPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_overview: dict[str, Any] | None = None
    scenarios: list[ScenarioEvaluationPatch] = Field(default_factory=list)


class EvaluationMetadata(BaseModel):
    module_name: str = "module_2_evaluator_rationalizer"
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evaluator_model: str
    prompt_version: str
    scenario_count: int


class EvaluationResult(BaseModel):
    metadata: EvaluationMetadata
    scenario_evaluations: list[ScenarioEvaluationPatch] = Field(default_factory=list)
