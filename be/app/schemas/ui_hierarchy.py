from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

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
    page_summary: str = Field(
        ..., description="Mô tả tổng quan UI"
    )
    business_intent: str = Field(
        ..., description="Mục tiêu business chính của màn hình (1-2 câu). Trả về chuỗi rỗng nếu không có interactive elements."
    )
    interactive_element_count: int = Field(
        ..., description="Tổng số element có thể tương tác"
    )


class ControlState(BaseModel):
    selected: Optional[bool] = Field(
        default=None, description="Trạng thái selected của tab hoặc option"
    )


class NavigationSignals(BaseModel):
    classification: Literal["in_scope_navigation", "out_of_scope", "ambiguous"] = Field(
        default="out_of_scope"
    )


class UINode(BaseModel):
    id: str = Field(..., description="Unique ID cho mỗi node (ví dụ: node_1, btn_submit)")
    kind: NodeKind = Field(
        ...,
        description=(
            "region / semantic_surface / component / control per ui-hierarchy-v2; "
            "text allowed for non-interactive copy the model may emit"
        ),
    )
    role: str = Field(
        ..., description="Vai trò chi tiết (ví dụ: button, link, textbox, checkbox, modal, list, dialog)"
    )
    semantic_lane: Optional[SemanticLane] = Field(
        default=None,
        description="Bắt buộc với kind semantic_surface trong prompt v2; optional ở đây để tolerante LLM",
    )
    surface_summary: Optional[str] = Field(
        default=None,
        description="Một dòng mô tả surface khi kind là semantic_surface",
    )
    functional_class: Optional[str] = Field(
        default=None, description="Ví dụ: menu_launcher, form_submit, pagination_control"
    )
    visible_text: Optional[str] = Field(
        default=None, description="Text hiển thị trên UI (trích xuất verbatim)"
    )
    verbatim_label_for_steps: Optional[str] = Field(
        default=None, description="Text được trích xuất verbatim cho Gherkin steps"
    )
    bdd_effective_scope: bool = Field(
        default=True, 
        description="Đánh dấu xem phần này có nằm trong trọng tâm BDD không (quan trọng khi có Modal, phần nền mờ đằng sau sẽ là false)"
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
    items: List[str] = Field(default_factory=list, description="List of control IDs in this group")
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
        description="Optional normalized stub from some pipelines (e.g. P-TEXT)",
    )


class SemanticIndexEntry(BaseModel):
    """One row per semantic_surface; lane-specific fields optional for tolerant parsing."""

    cluster_id: str = Field(..., description="ID của node semantic_surface tương ứng")
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
