"""Pydantic models for Stage C (BDD bundle) and Stage A output."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.behavior_flow import BehaviorFlowItem


class MachineProfile(BaseModel):
    primary_goal_hypothesis_stub: str = "unknown"
    domain_tags: list[str] = Field(default_factory=list)
    ambiguity_flags: list[str] = Field(default_factory=list)
    surface_role_echo: str = "unknown"


class BddFeatureBlockPtext(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    business_intent: str = ""
    machine_profile: MachineProfile | None = None

    @model_validator(mode="before")
    @classmethod
    def _default_machine_profile(cls, data: Any) -> Any:
        if isinstance(data, dict) and ("machine_profile" not in data or data["machine_profile"] is None):
            data = dict(data)
            data["machine_profile"] = MachineProfile().model_dump()
        return data


class BddScenarioCore(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    gherkin: str = Field(min_length=1)


class BddScenarioNormalized(BaseModel):
    model_config = {"extra": "ignore"}

    id: str = Field(min_length=1)
    scenario_taxonomy: str = "unknown"
    step_literals_quoted: list[str] = Field(default_factory=list)
    nav_destination_literal: str | None = None
    cohesive_form_cluster_id: str | None = None
    functional_group_id: str | None = None


class CrossScreenLinkageHypothesis(BaseModel):
    model_config = {"extra": "ignore"}

    kind: str = "ambiguous"
    evidence_snippet_verbatim: str = ""
    confidence: float = 0.0
    related_control_ids: list[str] = Field(default_factory=list)
    notes_for_downstream_ranker: str | None = None


class BddBundlePtext(BaseModel):
    feature: BddFeatureBlockPtext
    scenarios: list[BddScenarioCore] = Field(default_factory=list)
    scenarios_normalized: list[BddScenarioNormalized] = Field(default_factory=list)
    cross_screen_linkage_hypotheses: list[CrossScreenLinkageHypothesis] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _align_normalized(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        scenarios = data.get("scenarios") or []
        sn = list(data.get("scenarios_normalized") or [])
        if not isinstance(scenarios, list):
            return data
        by_id = {row["id"]: row for row in sn if isinstance(row, dict) and row.get("id")}
        for s in scenarios:
            if not isinstance(s, dict):
                continue
            sid = s.get("id")
            if sid and sid not in by_id:
                sn.append(
                    {
                        "id": sid,
                        "scenario_taxonomy": "unknown",
                        "step_literals_quoted": [],
                        "nav_destination_literal": None,
                        "cohesive_form_cluster_id": None,
                        "functional_group_id": None,
                    }
                )
                by_id[sid] = sn[-1]
        data["scenarios_normalized"] = sn
        if "cross_screen_linkage_hypotheses" not in data or data["cross_screen_linkage_hypotheses"] is None:
            data["cross_screen_linkage_hypotheses"] = []
        return data


class PtextPipelineResult(BaseModel):
    model: str
    flows: list[BehaviorFlowItem]
    captures: list[dict[str, Any]]
