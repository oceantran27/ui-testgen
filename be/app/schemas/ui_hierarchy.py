from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field

SemanticLane = Literal[
    "getting_input",
    "data_manipulation",
    "navigation",
    "content_structuring",
    "social_interaction",
    "system_utilities",
]

NodeKind = Literal["region", "component", "control", "semantic_surface", "text"]


class UIOverview(BaseModel):
    page_summary: str = Field(..., description="High-level English summary of the visible UI.")
    business_intent: str = Field(
        ...,
        description=(
            "Primary user or business goals for this screen (1–2 sentences). "
            "Return an empty string when there are no interactive elements."
        ),
    )
    interactive_element_count: int = Field(
        ...,
        description="Total count of interactive controls extracted (`kind: control`).",
    )


class ControlState(BaseModel):
    selected: Optional[bool] = Field(
        default=None,
        description="Whether a tab, radio option, or similar control appears selected.",
    )


class NavigationSignals(BaseModel):
    classification: Literal["in_scope_navigation", "out_of_scope", "ambiguous"] = Field(
        default="out_of_scope"
    )


class UINode(BaseModel):
    id: str = Field(..., description='Stable unique node id (e.g. "header_region", "btn_submit").')
    kind: NodeKind = Field(
        ...,
        description=(
            "region / semantic_surface / component / control per ui-hierarchy-v2; "
            "`text` is allowed for non-interactive copy the model may emit."
        ),
    )
    role: str = Field(
        ...,
        description='Concrete role (e.g. "button", "link", "textbox", "checkbox", "modal", "list", "dialog").',
    )
    semantic_lane: Optional[SemanticLane] = Field(
        default=None,
        description=(
            "Required when `kind` is `semantic_surface` in prompt v2; optional here for tolerant parsing."
        ),
    )
    surface_summary: Optional[str] = Field(
        default=None,
        description="One-line English summary when `kind` is `semantic_surface`.",
    )
    functional_class: Optional[str] = Field(
        default=None,
        description='Specialized class when applicable (e.g. "menu_launcher", "form_submit", "pagination_control").',
    )
    visible_text: Optional[str] = Field(
        default=None,
        description="Verbatim visible UI text; do not translate or normalize spelling.",
    )
    verbatim_label_for_steps: Optional[str] = Field(
        default=None,
        description="Verbatim label used in downstream natural-language test steps.",
    )
    scenario_effective_scope: bool = Field(
        default=True,
        validation_alias=AliasChoices("scenario_effective_scope", "bdd_effective_scope"),
        description=(
            "Whether this subtree is in scope for generating primary test scenarios. "
            "Background regions behind a modal with dimmed/disabled backdrop should be false."
        ),
    )
    state: Optional[ControlState] = None
    navigation_signals: Optional[NavigationSignals] = None
    children: List[UINode] = Field(default_factory=list)


class CohesiveForm(BaseModel):
    form_id: str
    heading_context: Optional[str] = None
    primary_submit_control_id: Optional[str] = None
    footer_action_control_ids: List[str] = Field(default_factory=list)


class FunctionalGroup(BaseModel):
    group_id: str
    items: List[str] = Field(default_factory=list, description="Control IDs belonging to this group.")
    first_visible_item_literal: Optional[str] = None


class SearchCluster(BaseModel):
    cluster_id: str
    input_id: Optional[str] = None
    button_id: Optional[str] = None


class NavigationDestination(BaseModel):
    control_id: str
    destination_label: str
    destination_canonical_stub: Optional[str] = Field(
        default=None,
        description="Optional normalized destination stub from auxiliary pipelines.",
    )


class SemanticIndexEntry(BaseModel):
    """One row per semantic_surface; lane-specific fields optional for tolerant parsing."""

    cluster_id: str = Field(..., description="Must match the corresponding `semantic_surface` node id.")
    semantic_lane: SemanticLane
    summary: str
    control_ids: List[str] = Field(default_factory=list)
    heading_context: Optional[str] = None
    footer_action_control_ids: List[str] = Field(default_factory=list)
    search_input_id: Optional[str] = None
    search_button_id: Optional[str] = None
    filter_control_ids: List[str] = Field(default_factory=list)
    sort_control_ids: List[str] = Field(default_factory=list)
    pagination_control_ids: List[str] = Field(default_factory=list)
    navigation_destinations: List[NavigationDestination] = Field(default_factory=list)
    content_pattern: Optional[str] = None
    first_visible_item_literal: Optional[str] = None


class UIDerived(BaseModel):
    semantic_index: List[SemanticIndexEntry] = Field(default_factory=list)
    cohesive_forms: List[CohesiveForm] = Field(default_factory=list)
    functional_groups: List[FunctionalGroup] = Field(default_factory=list)
    navigation_destinations: List[NavigationDestination] = Field(default_factory=list)
    search_clusters: List[SearchCluster] = Field(default_factory=list)


class UIHierarchyResult(BaseModel):
    schema_version: str = "ui-hierarchy-v2"
    overview: UIOverview
    root: UINode
    derived: UIDerived
