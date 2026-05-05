from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

SemanticLane = Literal[
    "getting_input",
    "data_manipulation",
    "navigation",
    "content_structuring",
    "social_interaction",
    "system_utilities",
]

class UIExtractionOverview(BaseModel):
    """Viewport-level overview from stage-1 UI extraction (flat schema)."""

    page: str = Field(..., description="English description of visible layout in the viewport.")
    intent_hint: str = Field(
        default="",
        description="Primary user goal on this screen; empty string when no interactive elements.",
    )
    control_count: int = Field(..., ge=0, description="Total interactive controls; must equal len(controls).")


class UIExtractedControl(BaseModel):
    id: str = Field(..., description='Stable control id (e.g. "btn_submit").')
    role: str = Field(..., description='ARIA-like role (e.g. "button", "textbox").')
    text: str = Field(default="", description="Verbatim visible text from the UI.")
    label: str = Field(default="", description="Readable label; mirror text or minimal literal for icon-only controls.")
    lane: SemanticLane
    type: Optional[str] = Field(default=None, description="Functional type when applicable (submit, search, filter, …).")
    scope: bool = Field(default=True, description="False when behind dimmed modal backdrop.")
    selected: Optional[bool] = Field(default=None, description="Visibly active/selected when applicable.")


class GroupSearchPair(BaseModel):
    input: str = Field(..., description="Control id of search input.")
    trigger: str = Field(..., description="Control id of search trigger (button/icon).")


class NavDestination(BaseModel):
    control: str = Field(..., description="Control id for the navigation affordance.")
    label: str = Field(..., description="Verbatim destination label.")


class ContentPattern(BaseModel):
    pattern: str = Field(..., description='e.g. "grid", "list", "card", "table", "tabs".')
    sample: str = Field(..., description="Verbatim text of the first representative item.")


class UISemanticGroup(BaseModel):
    id: str
    lane: SemanticLane
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
    schema_version: str = "ui-flat-v3"
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
    def _validate_counts_and_refs(self) -> UIExtractionResult:
        if self.overview.control_count != len(self.controls):
            raise ValueError("overview.control_count must equal len(controls)")
        control_ids = {c.id for c in self.controls}
        for g in self.groups:
            for cid in self._group_referenced_control_ids(g):
                if cid not in control_ids:
                    raise ValueError(f"group {g.id!r} references unknown control id {cid!r}")
        return self
