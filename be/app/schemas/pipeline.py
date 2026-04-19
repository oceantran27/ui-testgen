from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VisualGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    group_name: str = Field(..., min_length=1)
    elements: list[dict] = Field(default_factory=list)

    @field_validator("elements", mode="before")
    @classmethod
    def normalize_elements(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("elements must be a list")
        return [item for item in value if isinstance(item, dict)]


class VisualParserOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    visual_groups: list[VisualGroup]

    @field_validator("visual_groups", mode="before")
    @classmethod
    def normalize_visual_groups(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("visual_groups must be a list")
        return [item for item in value if isinstance(item, dict)]


class GherkinRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    given: str = Field(..., min_length=1)
    when: str = Field(..., min_length=1)
    then: str = Field(..., min_length=1)


class BusinessRuleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: GherkinRule
    element_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("element_ids", mode="before")
    @classmethod
    def normalize_element_ids(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("element_ids must be a list")

        normalized = [str(item).strip() for item in value if str(item).strip()]
        if not normalized:
            raise ValueError("element_ids must contain at least one id")
        return normalized


class BusinessRulesCategorized(BaseModel):
    model_config = ConfigDict(extra="forbid")

    Field_Level_Rules: list[BusinessRuleEntry] = Field(default_factory=list)
    State_Rules: list[BusinessRuleEntry] = Field(default_factory=list)
    Workflow_Rules: list[BusinessRuleEntry] = Field(default_factory=list)
    Validation_Rules: list[BusinessRuleEntry] = Field(default_factory=list)


class PageOverviewBusinessAnalyst(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_type: Literal[
        "form_submission",
        "dashboard_view",
        "data_table",
        "landing_page",
        "authentication",
        "checkout",
        "search",
        "settings",
        "unknown",
    ] = "unknown"
    primary_goal: str = ""
    functionality: str = ""
    target_users: str = ""



class BusinessAnalystOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_overview: PageOverviewBusinessAnalyst
    business_rules: BusinessRulesCategorized


class RawScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    user_goal: str = Field(..., min_length=1)
    category: Literal[
        "E2E_Workflow",
        "Form_Validation",
        "State_Transition",
        "Navigation",
    ]
    actor: str = Field(..., min_length=1)
    given: str = Field(..., min_length=1)
    when: str = Field(..., min_length=1)
    then: str = Field(..., min_length=1)
    expected_outcome: str = Field(..., min_length=1)
    step_order: int = Field(..., ge=1)
    referenced_element_ids: list[str] = Field(default_factory=list)
    source_rules: list[str] = Field(default_factory=list)
    visual_cues_expected: list[str] = Field(default_factory=list)
    verification_status: Literal["approved", "rejected"] = "approved"
    rejection_reason: str = ""
    verifier_confidence_score: float = Field(1.0, ge=0.0, le=1.0)

    @field_validator(
        "referenced_element_ids",
        "source_rules",
        "visual_cues_expected",
        mode="before",
    )
    @classmethod
    def normalize_string_lists(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("field must be a list")
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("referenced_element_ids")
    @classmethod
    def ensure_referenced_elements_present(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("referenced_element_ids must contain at least one id")
        return value

    @field_validator("source_rules")
    @classmethod
    def ensure_source_rules_present(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("source_rules must contain at least one rule reference")
        return value

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "RawScenario":
        # Keep reason semantics consistent with verifier output policy.
        reason = self.rejection_reason.strip()
        if self.verification_status == "rejected" and not reason:
            raise ValueError("rejection_reason must be provided when verification_status is rejected")
        if self.verification_status == "approved" and reason:
            raise ValueError("rejection_reason must be empty when verification_status is approved")
        self.rejection_reason = reason
        return self


class RawScenarioList(BaseModel):
    model_config = ConfigDict(extra="allow")

    scenarios: list[RawScenario] = Field(default_factory=list)
