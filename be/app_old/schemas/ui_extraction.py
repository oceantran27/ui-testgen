from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UIExtractionOverview(BaseModel):
    """Viewport-level overview from stage-1 UI extraction (flat schema, ui-flat-v5)."""

    viewport_description: str = Field(
        ...,
        description="Short English phrase: visible layout and purpose of the viewport.",
    )


class UIControlStates(BaseModel):
    """Optional per-control state flags; omit keys that do not apply."""

    model_config = ConfigDict(extra="ignore")

    selected: Optional[bool] = None
    disabled: Optional[bool] = None
    checked: Optional[bool] = None
    expanded: Optional[bool] = None


class UIExtractedControl(BaseModel):
    id: str = Field(..., description='Stable control id (e.g. "btn_submit").')
    role: str = Field(..., description='ARIA-like role (e.g. "button", "textbox").')
    label: str = Field(default="", description="Visual or inferred label for the control.")
    value: str = Field(
        default="",
        description="Verbatim visible text or current value; empty string if none.",
    )
    associated_context: str = Field(
        default="",
        description="Closest identifying context text near the control; empty if N/A.",
    )
    is_primary_layer: bool = Field(
        default=True,
        description="True on primary surface / topmost modal; false for clearly dimmed background.",
    )
    states: UIControlStates = Field(default_factory=UIControlStates)


class GroupSearchPair(BaseModel):
    input: str = Field(..., description="Control id of search input.")
    trigger: str = Field(..., description="Control id of search trigger (button/icon).")


class NavDestination(BaseModel):
    control: str = Field(..., description="Control id for the navigation affordance.")
    label: str = Field(..., description="Verbatim destination label.")


class ContentPattern(BaseModel):
    pattern: str = Field(..., description='e.g. "grid", "list", "card", "table", "tabs".')
    sample: str = Field(..., description="Verbatim text of one representative item.")


class UISemanticGroup(BaseModel):
    id: str
    summary: str = Field(..., description="One-line English purpose of the group.")
    controls: List[str] = Field(default_factory=list, description="Control ids in this semantic cluster.")

    primary_actions: Optional[List[str]] = None
    search: Optional[GroupSearchPair] = None
    filters: Optional[List[str]] = None
    sorts: Optional[List[str]] = None
    pagination: Optional[List[str]] = None
    destinations: Optional[List[NavDestination]] = None
    content: Optional[ContentPattern] = None


class UIExtractionResult(BaseModel):
    schema_version: str = "ui-flat-v5"
    overview: UIExtractionOverview
    controls: List[UIExtractedControl] = Field(default_factory=list)
    groups: List[UISemanticGroup] = Field(default_factory=list)

    @staticmethod
    def _group_referenced_control_ids(g: UISemanticGroup) -> List[str]:
        ids: List[str] = list(g.controls)
        if g.primary_actions:
            ids.extend(g.primary_actions)
        if g.search:
            ids.extend([g.search.input, g.search.trigger])
        if g.filters:
            ids.extend(g.filters)
        if g.sorts:
            ids.extend(g.sorts)
        if g.pagination:
            ids.extend(g.pagination)
        if g.destinations:
            ids.extend(d.control for d in g.destinations)
        return ids

    @model_validator(mode="after")
    def _validate_group_refs(self) -> UIExtractionResult:
        control_ids = {c.id for c in self.controls}
        for g in self.groups:
            for cid in self._group_referenced_control_ids(g):
                if cid not in control_ids:
                    raise ValueError(f"group {g.id!r} references unknown control id {cid!r}")
        return self
