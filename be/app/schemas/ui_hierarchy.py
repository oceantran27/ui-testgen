"""Pydantic models for Module 2 Agent 1: UI hierarchy extraction JSON."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UiHierarchyOverview(BaseModel):
    model_config = ConfigDict(extra="allow")

    page_summary: str = ""
    business_intent: str = ""
    interactive_element_count: int = Field(default=0, ge=0)


class UiHierarchyNode(BaseModel):
    """Recursive DOM-like node; LLM may attach extra fields per node."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    kind: str = ""
    children: list[UiHierarchyNode] = Field(default_factory=list)


class UiHierarchyDerived(BaseModel):
    """Summaries Agent 2 should prefer; tree remains authoritative for literals."""

    model_config = ConfigDict(extra="allow")

    cohesive_forms: list[dict[str, Any]] = Field(default_factory=list)
    functional_groups: list[dict[str, Any]] = Field(default_factory=list)
    navigation_destinations: list[dict[str, Any]] = Field(default_factory=list)


class UiHierarchyExtractionResult(BaseModel):
    """Agent 1 output contract (ui-hierarchy-v1)."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = "ui-hierarchy-v1"
    overview: UiHierarchyOverview = Field(default_factory=UiHierarchyOverview)
    root: UiHierarchyNode
    derived: UiHierarchyDerived = Field(default_factory=UiHierarchyDerived)
