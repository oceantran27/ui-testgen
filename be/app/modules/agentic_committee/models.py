from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentOpinion(BaseModel):
    score: int = Field(ge=1, le=10)
    rationale: str = Field(min_length=1)


class TargetedCritiques(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ba: str = ""
    qa: str = ""
    ux: str = ""


class JudgeRoundOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_converged: bool = False
    convergence_reason: str = ""
    compressed_context: str = ""
    targeted_critiques: TargetedCritiques = Field(default_factory=TargetedCritiques)


class FinalCommitteePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    BA_score: int = Field(ge=1, le=10)
    QA_score: int = Field(ge=1, le=10)
    UX_score: int = Field(ge=1, le=10)
    conflict_resolution_summary: str = Field(min_length=1)


class CommitteeState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scenario_id: str
    user_goal: str
    page_overview: dict[str, Any]
    scenario: dict[str, Any]
    model_name: str
    current_round: int = 0
    opinions_history: dict[int, dict[str, AgentOpinion]] = Field(default_factory=dict)
    compressed_context: str = ""
    targeted_critiques: TargetedCritiques = Field(default_factory=TargetedCritiques)
    is_converged: bool = False
    convergence_reason: str = ""
    final_payload: FinalCommitteePayload | None = None
