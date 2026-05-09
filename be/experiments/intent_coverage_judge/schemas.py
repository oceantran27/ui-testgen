"""Pydantic models for LLM-as-judge semantic intent coverage evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GroundTruthIntent(BaseModel):
    id: str = Field(min_length=1)
    intent_description: str = Field(
        min_length=1,
        description="Canonical user goal for this screen (wording need not match generated `intent`; judge uses gherkin quotes).",
    )


class GeneratedIntent(BaseModel):
    id: str = Field(min_length=1)
    intent: str = Field(
        min_length=1,
        description="Generalized imperative from the generator; specific UI strings appear in `gherkin` only.",
    )
    gherkin: str = Field(
        default="",
        description="Full Gherkin body; judge matches using quoted controls vs ground-truth semantics.",
    )


class GroundTruthScreenFile(BaseModel):
    image_id: str = Field(min_length=1)
    ground_truth_intents: list[GroundTruthIntent] = Field(default_factory=list)


class GeneratedScreenFile(BaseModel):
    image_id: str = Field(min_length=1)
    generated_intents: list[GeneratedIntent] = Field(default_factory=list)


class IntentMapping(BaseModel):
    generated_id: str
    ground_truth_id: str
    reasoning: str = Field(
        default="",
        description="Brief English; cite gherkin quotes / goals (per judge prompt).",
    )


class EvaluationResult(BaseModel):
    mappings: list[IntentMapping] = Field(default_factory=list)
    missing_ground_truth_ids: list[str] = Field(
        default_factory=list,
        description="Ground truth intent IDs that no generated intent adequately covers.",
    )
    extra_generated_ids: list[str] = Field(
        default_factory=list,
        description="Generated intent IDs that do not map to any ground truth (redundant or hallucinated).",
    )


class ScreenJudgeRecord(BaseModel):
    """One screen result persisted for audit."""

    image_id: str
    evaluation: EvaluationResult
    judge_seconds: float = 0.0
    validation_warnings: list[str] = Field(default_factory=list)
