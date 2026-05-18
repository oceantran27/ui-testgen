from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants.screen_intent_taxonomy import (
    EVIDENCE_TYPE_VALUES,
    INTENT_KIND_VALUES,
    MODEL_CONFIDENCE_VALUES,
    OPTION_REF_TYPE_VALUES,
    STEP_TYPE_VALUES,
    UNRESOLVED_REASON_VALUES,
    VISIBLE_STATUS_VALUES,
)
# Phase-2 draft enums (intent_kind, step_type, unresolved reason_code, …): canonical ordered lists live in
# app.constants.screen_intent_taxonomy — keep prompts aligned with those tuples, not duplicated literals here.

# ── UI state closed vocabularies (joint vision: prompt_joint_screen_understanding_v1) ──

A1ScreenType = Literal[
    "landing",
    "auth",
    "search",
    "listing",
    "detail",
    "form",
    "dashboard",
    "table",
    "cart",
    "checkout",
    "profile",
    "settings",
    "wizard_step",
    "document",
    "media",
    "support",
    "other",
]

A1PresentationScope = Literal[
    "full_screen",
    "modal",
    "drawer",
    "popover",
    "toast",
    "banner",
    "inline",
    "overlay",
    "unknown",
]

A1OutcomeStateType = Literal[
    "neutral",
    "success",
    "error",
    "validation_error",
    "warning",
    "empty",
    "loading",
    "confirmation_required",
    "review_required",
    "unknown",
]

A1VisualRegion = Literal[
    "top_bar",
    "navigation",
    "sidebar",
    "main",
    "footer",
    "bottom_bar",
    "dialog",
    "drawer",
    "popover",
    "toast",
    "overlay",
    "unknown",
]

A1ElementType = Literal[
    "heading",
    "text",
    "image",
    "icon",
    "button",
    "link",
    "input",
    "textarea",
    "select",
    "checkbox",
    "radio",
    "switch",
    "slider",
    "date_picker",
    "tab",
    "menu_item",
    "list",
    "list_item",
    "card",
    "table",
    "divider",
    "badge",
    "progress",
    "container",
    "other",
]

A1ActionType = Literal[
    "click",
    "type",
    "select",
    "toggle",
    "submit",
    "navigate",
    "open",
    "close",
    "confirm",
    "cancel",
    "upload",
    "drag",
    "scroll",
    "unknown",
]

A1FeedbackType = Literal[
    "success",
    "error",
    "validation_error",
    "warning",
    "info",
    "loading",
    "progress",
    "empty",
    "confirmation",
    "unknown",
]

A1GroupType = Literal[
    "form",
    "navigation",
    "search",
    "filter",
    "list",
    "list_item",
    "card",
    "table",
    "toolbar",
    "dialog",
    "feedback",
    "empty_state",
    "content_section",
    "media",
    "other",
]

A1GroupEvidenceType = Literal[
    "proximity",
    "common_region",
    "visual_similarity",
    "alignment",
    "explicit_container",
    "shared_label",
    "functional_relation",
]

A1RoleHint = Literal[
    "primary_action",
    "secondary_action",
    "required_input",
    "optional_input",
    "navigation",
    "informative",
    "status_indicator",
    "other",
]

A1ActionPriority = Literal["primary", "secondary", "tertiary"]

A1GroupConfidence = Literal["high", "medium", "low"]


class _PromptOutputBase(BaseModel):
    """Base class for all structured prompt outputs."""
    pass


# ──────────────────────────────────────────────
# Shared / Common
# ──────────────────────────────────────────────

class SourceElementRefA2(_PromptOutputBase):
    state_id: str
    element_id: str


class VisualDeltaRef(_PromptOutputBase):
    transition_id: str
    delta_description: str


# ──────────────────────────────────────────────
# UI State Extraction V2 shape (embedded in JointScreenUnderstandingResult)
# ──────────────────────────────────────────────


class GroupEvidenceA1V2(_PromptOutputBase):
    evidence_type: A1GroupEvidenceType
    description: str


class UIElementA1V2(_PromptOutputBase):
    element_id: str
    element_type: A1ElementType
    text: List[str] = Field(default_factory=list)
    role_hint: Optional[A1RoleHint] = None
    visual_region: A1VisualRegion = "unknown"


class UIActionA1V2(_PromptOutputBase):
    action_id: str
    action_type: A1ActionType
    text: List[str] = Field(default_factory=list)
    action_priority: Optional[A1ActionPriority] = None
    visual_region: A1VisualRegion = "unknown"


class UIFeedbackA1V2(_PromptOutputBase):
    feedback_id: str
    feedback_type: A1FeedbackType
    text: List[str] = Field(default_factory=list)
    related_element_ids: List[str] = Field(default_factory=list)
    visual_region: A1VisualRegion = "unknown"


class InteractionGroupA1V2(_PromptOutputBase):
    group_id: str
    group_type: A1GroupType
    group_label: Optional[str] = None
    element_ids: List[str] = Field(default_factory=list)
    action_ids: List[str] = Field(default_factory=list)
    feedback_ids: List[str] = Field(default_factory=list)
    primary_action_id: Optional[str] = None
    group_evidence: List[GroupEvidenceA1V2] = Field(default_factory=list)
    group_confidence: A1GroupConfidence


class UIStateExtractionV2Result(_PromptOutputBase):
    state_id: str
    screen_purpose: str
    presentation_scope: A1PresentationScope = "unknown"
    screen_type: A1ScreenType
    outcome_state_type: A1OutcomeStateType = "neutral"
    domain: str
    visible_elements: List[UIElementA1V2] = Field(default_factory=list)
    available_actions: List[UIActionA1V2] = Field(default_factory=list)
    visible_feedback: List[UIFeedbackA1V2] = Field(default_factory=list)
    interaction_groups: List[InteractionGroupA1V2] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A2 v2: Screen Behaviour Intent Extraction (NEW)
# ──────────────────────────────────────────────


class ScreenIntentPrimaryActionA2(_PromptOutputBase):
    """Hydrated action reference — populated from Phase 1 `available_actions` by backend."""

    action_id: Optional[str] = Field(default=None)
    action_type: str
    text: List[str] = Field(default_factory=list)


class EvidenceRefDraftA2(_PromptOutputBase):
    """LLM output: evidence grounding by ID only; backend hydrates `text`."""

    evidence_type: str
    source_id: str

    @field_validator("evidence_type")
    @classmethod
    def _evidence_kind(cls, v: str) -> str:
        v = str(v).strip()
        if v not in EVIDENCE_TYPE_VALUES:
            raise ValueError(f"unsupported evidence_type {v!r}")
        return v


class EvidenceRefHydratedA2(_PromptOutputBase):
    evidence_type: str
    source_id: str
    text: List[str] = Field(default_factory=list)


class UnresolvedScreenGroupA2(_PromptOutputBase):
    group_id: str
    reason_code: str
    details: str = ""

    @field_validator("reason_code")
    @classmethod
    def _reason_code_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in UNRESOLVED_REASON_VALUES:
            raise ValueError(f"unsupported reason_code {v!r}")
        return v


class SelectionOptionDraftA2(_PromptOutputBase):
    option_ref_type: str
    option_element_id: Optional[str] = None
    option_action_id: Optional[str] = None
    visible_status: str = "unknown"

    @field_validator("option_ref_type")
    @classmethod
    def _opt_ref_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in OPTION_REF_TYPE_VALUES:
            raise ValueError(f"unsupported option_ref_type {v!r}")
        return v

    @field_validator("visible_status")
    @classmethod
    def _vis_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in VISIBLE_STATUS_VALUES:
            raise ValueError(f"unsupported visible_status {v!r}")
        return v


class SelectionOptionA2(_PromptOutputBase):
    """Hydrated selection option incl. duplicated text from Phase 1 objects."""

    option_ref_type: str
    option_element_id: Optional[str] = None
    option_action_id: Optional[str] = None
    option_text: List[str] = Field(default_factory=list)
    visible_status: str = "unknown"


class ActionSequenceStepDraftA2(_PromptOutputBase):
    """LLM step in local_action_sequence_templates; step_type whitelist = STEP_TYPE_VALUES in screen_intent_taxonomy."""

    step_type: str
    source_action_id: Optional[str] = None
    source_element_id: Optional[str] = None

    @field_validator("step_type")
    @classmethod
    def _step_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in STEP_TYPE_VALUES:
            raise ValueError(f"unsupported step_type {v!r}")
        return v


class ActionSequenceStepA2(_PromptOutputBase):
    step_type: str
    source_action_id: Optional[str] = None
    source_element_id: Optional[str] = None
    text: List[str] = Field(default_factory=list)


class ActionSequenceTemplateDraftA2(_PromptOutputBase):
    sequence_name: str
    steps: List[ActionSequenceStepDraftA2] = Field(default_factory=list)
    outcome_prediction_allowed: bool = False


class ActionSequenceTemplateA2(_PromptOutputBase):
    sequence_name: str
    steps: List[ActionSequenceStepA2] = Field(default_factory=list)
    outcome_prediction_allowed: bool = False


class ScreenBehaviourIntentDraftA2(_PromptOutputBase):
    """Structured LLM output (IDs only for actions/evidence/options). Backend validates + hydrates."""

    source_group_id: str
    intent_kind: str
    intent_name: str
    local_user_goal: str
    primary_action_id: Optional[str] = None
    commit_action_id: Optional[str] = None
    secondary_action_ids: List[str] = Field(default_factory=list)
    selection_options: List[SelectionOptionDraftA2] = Field(default_factory=list)
    local_action_sequence_templates: List[ActionSequenceTemplateDraftA2] = Field(default_factory=list)
    required_input_element_ids: List[str] = Field(default_factory=list)
    evidence_refs: List[EvidenceRefDraftA2] = Field(default_factory=list)
    model_confidence: str = "medium"

    @field_validator("intent_kind")
    @classmethod
    def _intent_kind_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in INTENT_KIND_VALUES:
            raise ValueError(f"unsupported intent_kind {v!r}")
        return v

    @field_validator("model_confidence")
    @classmethod
    def _model_conf_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in MODEL_CONFIDENCE_VALUES:
            raise ValueError(f"unsupported model_confidence {v!r}")
        return v


class ScreenIntentExtractionV2Result(_PromptOutputBase):
    screen_behaviour_intents: List[ScreenBehaviourIntentDraftA2] = Field(default_factory=list)
    unresolved_screen_groups: List[UnresolvedScreenGroupA2] = Field(default_factory=list)


class JointScreenUnderstandingResult(_PromptOutputBase):
    """Single vision structured output: UI evidence (A1) + local intents (A2 drafts)."""

    ui_state: UIStateExtractionV2Result
    screen_intents: ScreenIntentExtractionV2Result


class ScreenBehaviourIntentA2(_PromptOutputBase):
    """Validated hydrated catalog consumed by downstream (flow context / edges / audits)."""

    screen_intent_id: str
    source_state_id: str
    source_group_id: str
    intent_name: str
    intent_kind: str
    local_user_goal: str
    primary_action: Optional[ScreenIntentPrimaryActionA2] = None
    selection_options: List[SelectionOptionA2] = Field(default_factory=list)
    commit_action: Optional[ScreenIntentPrimaryActionA2] = None
    secondary_actions: List[ScreenIntentPrimaryActionA2] = Field(default_factory=list)
    local_action_sequence_templates: List[ActionSequenceTemplateA2] = Field(default_factory=list)
    required_input_element_ids: List[str] = Field(default_factory=list)
    evidence_refs: List[EvidenceRefHydratedA2] = Field(default_factory=list)
    evidence: List[str] = Field(
        default_factory=list,
        description="Short verbatim-style summaries derived from hydrated evidence_refs (legacy-compatible).",
    )
    model_confidence: str = "medium"
    validation_confidence: str = "medium"
    confidence: str = "medium"



# ──────────────────────────────────────────────
# A3: UI Flow Discovery / intent-aware flows (prompt: prompt_intent_aware_flow_discovery)
# ──────────────────────────────────────────────

FLOW_DISCOVERY_FLOW_TYPES: frozenset[str] = frozenset(
    {"single_step_outcome", "ordered_sequence", "branching_flow"}
)

GLOBAL_FLOW_DISCOVERY_STEP_ROLES: frozenset[str] = frozenset(
    {
        "entry",
        "intermediate",
        "review",
        "outcome_success",
        "outcome_error",
        "outcome_validation",
        "confirmation_surface",
        "terminal_success",
        "terminal_failure",
        "isolated",
    }
)


EDGE_DECISION_REASON_CODES: frozenset[str] = frozenset(
    {
        "selected_high_score_edge",
        "selected_medium_score_edge",
        "negative_outcome_branch",
        "recovery_navigation",
        "local_only_no_target",
        "contradicted_visible_evidence",
        "ambiguous_target",
        "insufficient_evidence",
        "conflicting_order",
        "weak_semantic_fit",
    }
)

SEMANTIC_CLUSTER_REASON_CODES: frozenset[str] = frozenset(
    {
        "same_task_area",
        "same_domain",
        "same_screen_family",
        "similar_feedback",
        "shared_user_goal",
    }
)


class FlowTransitionTriggerA3(_PromptOutputBase):
    """Hydrated trigger shape stored on FlowTransition.trigger_json (not LLM-authored)."""

    action_type: str
    text: List[str] = Field(default_factory=list)


class EdgeDecisionA4(_PromptOutputBase):
    candidate_edge_id: str
    decision: Literal["accepted", "rejected", "local_interaction", "uncertain"]
    bucket: Literal[
        "direct_transition",
        "alternative_outcome",
        "local_interaction",
        "uncertain_relation",
        "rejected",
    ]
    reason_code: str
    evidence_level: Literal["strong", "medium"]
    notes: Optional[str] = None

    @field_validator("reason_code")
    @classmethod
    def _reason_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in EDGE_DECISION_REASON_CODES:
            raise ValueError(f"unsupported edge_decision reason_code {v!r}")
        return v


class FlowDiscoveryA3(_PromptOutputBase):
    """LLM composes flows using existing candidate_edge_id values only."""

    flow_id: str
    flow_name: str
    flow_type: str  # single_step_outcome | ordered_sequence | branching_flow
    user_goal: str
    ordered_states: List[str] = Field(default_factory=list)
    transition_edge_ids: List[str] = Field(default_factory=list)
    alternative_outcome_edge_ids: List[str] = Field(default_factory=list)
    local_interaction_edge_ids: List[str] = Field(default_factory=list)
    uncertain_edge_ids: List[str] = Field(default_factory=list)
    flow_validation_status: Optional[str] = None  # valid | invalid | repaired (backend)

    @field_validator("flow_type")
    @classmethod
    def _flow_type_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in FLOW_DISCOVERY_FLOW_TYPES:
            raise ValueError(f"unsupported flow_type {v!r}")
        return v


class SemanticClusterA3(_PromptOutputBase):
    cluster_id: str
    domain: str
    states: List[str] = Field(default_factory=list)
    reason_code: str
    notes: Optional[str] = None

    @field_validator("reason_code")
    @classmethod
    def _cluster_reason_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in SEMANTIC_CLUSTER_REASON_CODES:
            raise ValueError(f"unsupported semantic cluster reason_code {v!r}")
        return v


class UncertainRelationA3(_PromptOutputBase):
    candidate_edge_id: str
    reason_code: str
    notes: Optional[str] = None

    @field_validator("reason_code")
    @classmethod
    def _uncertain_reason_vocab(cls, v: str) -> str:
        v = str(v).strip()
        if v not in EDGE_DECISION_REASON_CODES:
            raise ValueError(f"unsupported uncertain_relations reason_code {v!r}")
        return v


class UIFlowDiscoveryResult(_PromptOutputBase):
    flow_discovery_result_id: Optional[str] = None
    source_canonical_state_set_id: Optional[str] = None
    edge_decisions: List[EdgeDecisionA4] = Field(default_factory=list)
    candidate_flows: List[FlowDiscoveryA3] = Field(default_factory=list)
    semantic_clusters: List[SemanticClusterA3] = Field(default_factory=list)
    uncertain_relations: List[UncertainRelationA3] = Field(default_factory=list)
    discovery_warnings: List[str] = Field(default_factory=list)


# ── compressed_catalog_v2 (deterministic shrink for global_flow_discovery input) ──

CompressedContinuityEntityType = Literal[
    "product",
    "service",
    "user",
    "order",
    "appointment",
    "date",
    "time",
    "amount",
    "location",
    "document",
    "unknown",
]


class CompressedTaxonomy(_PromptOutputBase):
    domain: str
    screen_type: A1ScreenType
    presentation_scope: A1PresentationScope
    outcome_state_type: A1OutcomeStateType


class CompressedVisibleSignature(_PromptOutputBase):
    headings: List[str] = Field(default_factory=list)
    primary_texts: List[str] = Field(default_factory=list)
    status_texts: List[str] = Field(default_factory=list)


class CompressedNavigationCues(_PromptOutputBase):
    breadcrumb_texts: List[str] = Field(default_factory=list)
    active_tab_text: Optional[str] = None
    step_label_text: Optional[str] = None
    step_index_visible: Optional[int] = None
    step_total_visible: Optional[int] = None
    progress_text: Optional[str] = None


class CompressedStateFeedbackItem(_PromptOutputBase):
    feedback_id: str
    feedback_type: A1FeedbackType
    text: List[str] = Field(default_factory=list)
    related_element_ids: List[str] = Field(default_factory=list)
    visual_region: str = "unknown"


class CompressedFormField(_PromptOutputBase):
    element_id: str
    text: List[str] = Field(default_factory=list)


class CompressedFormSelectionOption(_PromptOutputBase):
    option_ref_type: Literal["element", "action"]
    option_element_id: Optional[str] = None
    option_action_id: Optional[str] = None
    text: List[str] = Field(default_factory=list)
    visible_status: str = "unknown"


class CompressedFormStateSummary(_PromptOutputBase):
    has_form: bool
    required_inputs: List[CompressedFormField] = Field(default_factory=list)
    optional_inputs: List[CompressedFormField] = Field(default_factory=list)
    selected_options: List[CompressedFormSelectionOption] = Field(default_factory=list)
    has_visible_values: bool
    has_validation_feedback: bool


class CompressedContinuityEntity(_PromptOutputBase):
    entity_type: CompressedContinuityEntityType
    text: List[str] = Field(default_factory=list)
    source_element_id: Optional[str] = None


class CompressedActionRef(_PromptOutputBase):
    action_id: str
    action_type: str
    text: List[str] = Field(default_factory=list)
    priority: A1ActionPriority


class CompressedEvidenceRef(_PromptOutputBase):
    evidence_type: str
    source_id: str


class CompressedLocalActionStep(_PromptOutputBase):
    step_type: str
    source_action_id: Optional[str] = None
    source_element_id: Optional[str] = None


class CompressedIntentGroup(_PromptOutputBase):
    intent_id: str
    source_group_id: str
    intent_kind: str
    intent_name: str
    local_user_goal: str
    # Each row: [action_id, action_type, action_text, value, status] for LLM / discovery (selection + primary).
    actions: List[Tuple[str, str, str, str, str]] = Field(default_factory=list)
    primary_action: Optional[CompressedActionRef] = None
    commit_action: Optional[CompressedActionRef] = None
    secondary_actions: List[CompressedActionRef] = Field(default_factory=list)
    selection_options: List[CompressedFormSelectionOption] = Field(default_factory=list)
    local_action_sequence: List[CompressedLocalActionStep] = Field(default_factory=list)
    required_input_element_ids: List[str] = Field(default_factory=list)
    feedback_refs: List[str] = Field(default_factory=list)
    evidence_refs: List[CompressedEvidenceRef] = Field(default_factory=list)


class CompressedScreenCard(_PromptOutputBase):
    state_id: str
    screen_purpose: str
    taxonomy: CompressedTaxonomy
    visible_signature: CompressedVisibleSignature
    navigation_cues: CompressedNavigationCues
    state_feedback_summary: List[CompressedStateFeedbackItem] = Field(default_factory=list)
    form_state_summary: CompressedFormStateSummary
    continuity_entities: List[CompressedContinuityEntity] = Field(default_factory=list)
    intent_groups: List[CompressedIntentGroup] = Field(default_factory=list)
    evidence_refs: List[CompressedEvidenceRef] = Field(default_factory=list)


class CompressedTraceIndexEntry(_PromptOutputBase):
    source_image_id: str
    ui_state_package_ref: str
    screen_intent_package_ref: str


class CompressedCatalogPackage(_PromptOutputBase):
    """Phase 1+2 → token-shaped catalogue for batched global flow discovery (compressed_catalog_v2)."""

    catalog_version: Literal["compressed_catalog_v2"] = "compressed_catalog_v2"
    catalog_purpose: Literal["global_flow_discovery_input"] = "global_flow_discovery_input"
    compressed_catalog_package_id: str = ""
    compressed_catalog: List[CompressedScreenCard] = Field(default_factory=list)
    trace_index: Dict[str, CompressedTraceIndexEntry] = Field(default_factory=dict)
    compression_stats: Dict[str, Any] = Field(default_factory=dict)


class FlowDiscoveryTriggerAction(_PromptOutputBase):
    """Resolved trigger on a flow step — action ids must exist on the source state's catalogue card."""

    intent_id: Optional[str] = None
    action_id: str = ""
    action_type: str = ""
    text: List[str] = Field(default_factory=list)


class FlowDiscoveryStep(_PromptOutputBase):
    state_id: str
    step_role: str = "intermediate"
    next_trigger_action: Optional[FlowDiscoveryTriggerAction] = None

    @field_validator("step_role")
    @classmethod
    def _step_role_vocab(cls, v: str) -> str:
        v = str(v or "").strip() or "intermediate"
        if v not in GLOBAL_FLOW_DISCOVERY_STEP_ROLES:
            return "intermediate"
        return v


class FlowDiscoveryAlternativeOutcome(_PromptOutputBase):
    from_state_id: str
    to_state_id: str
    outcome_role: str = ""
    trigger_action: Optional[FlowDiscoveryTriggerAction] = None
    evidence_summary: str = ""


class FlowDiscoveryEvidence(_PromptOutputBase):
    evidence_type: str = ""
    from_state_id: str = ""
    to_state_id: str = ""
    source_refs: List[str] = Field(default_factory=list)


class FlowDiscoverySemanticCluster(_PromptOutputBase):
    cluster_id: str
    cluster_goal: str = ""
    domain: str = ""
    state_ids: List[str] = Field(default_factory=list)
    cluster_evidence: List[str] = Field(default_factory=list)


class FlowDiscoveryCandidateFlow(_PromptOutputBase):
    """One composed behavioural flow candidate from compressed UI state cards."""

    flow_id: str
    flow_name: str = ""
    flow_type: str  # single_step_outcome | ordered_sequence | branching_flow
    user_goal: str = ""
    flow_confidence: str = "medium"
    ordered_steps: List[FlowDiscoveryStep] = Field(default_factory=list)
    ordered_states: List[str] = Field(default_factory=list)
    alternative_outcomes: List[FlowDiscoveryAlternativeOutcome] = Field(default_factory=list)
    flow_evidence: List[FlowDiscoveryEvidence] = Field(default_factory=list)
    entry_state_id: str = ""
    terminal_outcome: Optional[str] = None
    rationale: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_confidence(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            fc = data.get("flow_confidence")
            if fc in (None, "") and data.get("confidence") not in (None, ""):
                data["flow_confidence"] = data.get("confidence")
        return data

    @field_validator("flow_type")
    @classmethod
    def _flow_type_vocab_compressed(cls, v: str) -> str:
        v = str(v).strip()
        if v not in FLOW_DISCOVERY_FLOW_TYPES:
            raise ValueError(f"unsupported flow_type {v!r}")
        return v

    @property
    def confidence(self) -> str:
        """Backward-compatible alias used when assembling bridge payloads."""

        return str(self.flow_confidence or "medium")


class FlowDiscoveryUnassignedState(_PromptOutputBase):
    state_id: str
    reason_code: str = ""
    notes: Optional[str] = None


class UncertainRelationGlobal(_PromptOutputBase):
    """Loose linkage the model cannot place in ordered_steps."""

    from_state_id: Optional[str] = None
    to_state_id: Optional[str] = None
    reason_code: str = ""
    notes: Optional[str] = None


class GlobalFlowDiscoveryResult(_PromptOutputBase):
    """Structured output from prompt_global_flow_discovery (compressed behavioural cards)."""

    semantic_clusters: List[FlowDiscoverySemanticCluster] = Field(default_factory=list)
    candidate_flows: List[FlowDiscoveryCandidateFlow] = Field(default_factory=list)
    unassigned_state_ids: List[FlowDiscoveryUnassignedState] = Field(default_factory=list)
    uncertain_relations: List[UncertainRelationGlobal] = Field(default_factory=list)
    discovery_warnings: List[str] = Field(default_factory=list)


# Legacy aliases (removed types): use FlowDiscoveryCandidateFlow / FlowDiscoveryStep.


# ──────────────────────────────────────────────
# A4–A5: Behaviour contract / intent inference (prompt: prompt_behaviour_contract_builder)
# ──────────────────────────────────────────────

class IntentReadinessA3(_PromptOutputBase):
    readiness_level: str  # ready_for_intent, partial_intent_only, capability_only, not_ready
    reason: str
    usable_for_primary_scenario: bool


class ActionSequenceStepEdge(_PromptOutputBase):
    source_state: str
    source_group_id: Optional[str] = None
    source_screen_intent_id: Optional[str] = None
    source_action_id: Optional[str] = None
    source_element_id: Optional[str] = None
    action_role: str  # select_option | input | commit | confirm | cancel | navigate
    action_text: List[str] = Field(default_factory=list)


class EdgeContextParameter(_PromptOutputBase):
    name: str
    value: str
    evidence: List[str] = Field(default_factory=list)


class TransitionEvidenceVLMResult(_PromptOutputBase):
    """
    Pairwise screenshot transition evidence (Agent 3.5).
    After VLM classification, downstream marks proposal_status / vlm_confidence on the candidate edge dict.
    """

    transition_supported: bool
    confidence: Literal["high", "medium", "low"]
    evidence_level: Literal["strong", "medium"]
    visible_delta_summary: str = ""
    mismatch_reason: Optional[str] = None
    alternative_interpretation: Optional[str] = None


class CandidateEdge(_PromptOutputBase):
    edge_id: str
    from_state: str
    to_state: str
    edge_kind: str  # progress | success_terminal | empty_result | validation_error | warning | error | failure | confirmation_required | review_required | (+ legacy composer tokens if persisted downstream)
    scenario_role: str  # core | branch | optional | excluded
    action_scope: str = "task_core"
    scenario_branch_role: str = "core_progress"
    scenario_worthiness_score: int = 0
    scenario_worthiness_reasons: List[str] = Field(default_factory=list)
    excluded_from_agent4_payload: bool = False
    action_sequence: List[ActionSequenceStepEdge] = Field(default_factory=list)
    alternative_action_sequences: List[List[ActionSequenceStepEdge]] = Field(default_factory=list)
    context_parameters: List[EdgeContextParameter] = Field(default_factory=list)
    source_visible_evidence: List[str] = Field(default_factory=list)
    target_visible_evidence: List[str] = Field(default_factory=list)
    confidence: str = "medium"
    exclusion_reason: Optional[str] = None
    edge_score: float = 0.0  # 0–100 resolver heuristic after gates
    edge_score_reasons: List[str] = Field(default_factory=list)
    edge_risk_flags: List[str] = Field(default_factory=list)


class ComposedEdge(CandidateEdge):
    """An edge that has been validated and selected for a path."""
    pass


class ComposedFlowSourceTraceStep(_PromptOutputBase):
    """Trace row for intermediate composed-flow provenance."""

    candidate_edge_id: Optional[str] = None
    transition_id: Optional[str] = None
    bucket: Optional[str] = None
    reason_code: Optional[str] = None


class ComposedFlowInternal(_PromptOutputBase):
    """
    Backend-only composed flow handed to BehaviourIntent mapper.
    edge_sequence mirrors hydrated transition dicts (extra keys tolerated).
    """

    model_config = ConfigDict(extra="ignore")

    composed_flow_id: str
    source_flow_id: str
    source_flow_name: str
    user_goal: str = ""
    source_discovery_flow_type: str = ""
    flow_type: str  # main_success_path | validation_branch | error_branch | empty_result_branch | cancellation_branch | recovery_branch | navigation_branch | ...
    start_state: str
    end_state: str
    state_path: List[str] = Field(default_factory=list)
    edge_sequence: List[Dict[str, Any]] = Field(default_factory=list)
    source_trace: List[ComposedFlowSourceTraceStep] = Field(default_factory=list)
    composition_method: str  # agent4_selected_edges
    confidence: str
    behaviour_name: str
    source_group_id: Optional[str] = None
    source_screen_intent_id: Optional[str] = None


class ComposedFlowA5(_PromptOutputBase):
    composed_flow_id: str
    source_flow_id: str
    source_flow_name: str
    flow_type: str  # main_success_path | negative_branch | alternative_branch | validation_branch | error_branch | recovery_branch | independent_flow (+ empty_result_branch, cancellation_branch, navigation_branch per internal composer)
    start_state: str
    end_state: str
    state_path: List[str] = Field(default_factory=list)
    edge_sequence: List[ComposedEdge] = Field(default_factory=list)
    behaviour_name: str
    confidence: str


class TriggerActionA5(_PromptOutputBase):
    action_type: str
    text: List[str] = Field(default_factory=list)


class TestDataRequirementA5(_PromptOutputBase):
    field_or_input: str
    value_type: str
    reason: str
    required: bool


class BehaviourIntentA5(_PromptOutputBase):
    intent_id: str
    source_flow_id: str
    source_flow_name: str
    source_flow_type: str  # single_step_outcome | ordered_sequence | branching_flow
    composition_method: Optional[str] = None  # agent4_selected_edges
    flow_validation_status: Optional[str] = None  # valid | invalid | repaired
    min_scenario_worthiness: Optional[int] = None
    scenario_worthy_path: bool = True
    source_transition_indexes: List[int] = Field(default_factory=list)
    source_outcome_state: Optional[str] = None
    source_group_id: Optional[str] = None
    source_screen_intent_id: Optional[str] = None
    source_transition_ids: List[str] = Field(default_factory=list)
    behaviour_name: str
    intent_type: str  # positive | negative | validation | navigation | recovery | registration | access_control | data_entry | unknown
    user_intent: str
    business_goal: str
    start_state: str
    end_state: str
    trigger_action: TriggerActionA5
    preconditions: List[str] = Field(default_factory=list)
    test_data_requirements: List[TestDataRequirementA5] = Field(default_factory=list)
    user_actions: List[str] = Field(default_factory=list)
    expected_result: str
    expected_ui_evidence: List[str] = Field(default_factory=list)
    negative_expectations: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: str  # high | medium | low


class UnresolvedFlowItemA5(_PromptOutputBase):
    item_type: str  # semantic_cluster | uncertain_relation | unsupported_flow | unsupported_transition | unmatched_branch_outcome
    source_id: Optional[str] = None
    related_states: List[str] = Field(default_factory=list)
    reason: str


class GenerationSummaryA5(_PromptOutputBase):
    total_candidate_flows: int
    total_behaviour_intents: int
    total_unresolved_items: int
    behaviour_intents_created: int = 0
    skipped_due_to_invalid_flow: int = 0
    skipped_due_to_non_scenario_worthy_edge: int = 0


class BehaviourIntentInferenceResult(_PromptOutputBase):
    behaviour_intents: List[BehaviourIntentA5] = Field(default_factory=list)
    unresolved_flow_items: List[UnresolvedFlowItemA5] = Field(default_factory=list)
    generation_summary: GenerationSummaryA5


AnchorMatchModeA6 = Literal["exact", "exact_or_contained"]


class MandatoryAnchorA6(_PromptOutputBase):
    anchor_id: str
    text: str
    source: str = ""
    match_type: AnchorMatchModeA6 = "exact_or_contained"


class MandatoryAnchorsBySectionA6(_PromptOutputBase):
    given: List[MandatoryAnchorA6] = Field(default_factory=list)
    when: List[MandatoryAnchorA6] = Field(default_factory=list)
    then: List[MandatoryAnchorA6] = Field(default_factory=list)


class ForbiddenContentPolicyA6(_PromptOutputBase):
    no_new_ui_actions: bool = True
    no_new_screens: bool = True
    no_real_credentials: bool = True
    no_backend_assumptions: bool = True


class BlueprintTraceabilityA6(_PromptOutputBase):
    trigger_action_id: Optional[str] = None
    source_screen_intent_id: Optional[str] = None
    source_transition_ids: List[str] = Field(default_factory=list)
    expected_feedback_ids: List[str] = Field(default_factory=list)


class BlueprintTerminalStateRefA6(_PromptOutputBase):
    state_id: str
    screen_label: str = ""
    outcome_state_type: Optional[str] = None


class BlueprintHiddenAssertionA6(_PromptOutputBase):
    """Internal / causal assertions kept for audit — not mandatory Gherkin Then anchors."""

    assertion_type: str = "internal"
    expected: str
    render_in_gherkin: bool = False
    ui_text_grounding_required: bool = False


class ScenarioWritingBlueprint(_PromptOutputBase):
    blueprint_id: str
    source_intent_id: str
    source_flow_id: str
    scenario_type: str = "happy_path"
    start_state: BlueprintTerminalStateRefA6
    end_state: BlueprintTerminalStateRefA6
    writing_goal: str = ""
    mandatory_anchors: MandatoryAnchorsBySectionA6 = Field(default_factory=MandatoryAnchorsBySectionA6)
    allowed_test_data_placeholders: List[str] = Field(default_factory=list)
    hidden_assertions: List[BlueprintHiddenAssertionA6] = Field(default_factory=list)
    forbidden_content_policy: ForbiddenContentPolicyA6 = Field(default_factory=ForbiddenContentPolicyA6)
    traceability: BlueprintTraceabilityA6 = Field(default_factory=BlueprintTraceabilityA6)


class ScenarioBlueprintWritingStyleA6(_PromptOutputBase):
    tone: str = "clear QA BDD"
    avoid_mechanical_state_ids: bool = True
    use_natural_step_text: bool = True


class ScenarioBlueprintBatchInput(_PromptOutputBase):
    scenario_writing_blueprints: List[ScenarioWritingBlueprint] = Field(default_factory=list)
    writing_style: ScenarioBlueprintWritingStyleA6 = Field(default_factory=ScenarioBlueprintWritingStyleA6)


# ──────────────────────────────────────────────
# A6: BDD Scenario Generation (scenario_generation.txt)
# ──────────────────────────────────────────────

class TestDataA6(_PromptOutputBase):
    data_name: str
    value_placeholder: str
    source_requirement: str
    required: bool
    reason: str


class TestScenarioStepA6(_PromptOutputBase):
    step_number: int
    keyword: str  # Given | When | Then | And
    text: str
    source: str  # precondition | test_data | user_action | expected_result | expected_ui_evidence | negative_expectation
    anchor_ids_used: List[str] = Field(default_factory=list)


class AssertionA6(_PromptOutputBase):
    assertion_type: str  # state_reached | state_transition | feedback_visible | screen_type_visible | screen_purpose_matched | ui_evidence_present | state_not_reached | feedback_not_visible | unknown
    expected: str
    source: str  # expected_result | expected_ui_evidence | negative_expectation
    ui_text_grounding_required: Optional[bool] = None  # False: skip verbatim UI pool matching in Agent 7 pre-audit counts
    render_in_gherkin: bool = True
    anchor_ids_used: List[str] = Field(default_factory=list)


class GroundingContractA6(_PromptOutputBase):
    required_anchor_ids: List[str] = Field(default_factory=list)
    used_anchor_ids: List[str] = Field(default_factory=list)


class PreGenerationGroundingA6(_PromptOutputBase):
    """Keyword-anchor validation emitted before Agent 7 (experimental metrics)."""

    required_anchor_count: int = 0
    matched_anchor_count: int = 0
    missing_anchor_ids: List[str] = Field(default_factory=list)
    wrong_section_anchor_ids: List[str] = Field(default_factory=list)
    unexpected_placeholders: List[str] = Field(default_factory=list)
    invalid_trace_refs: List[str] = Field(default_factory=list)
    matched_anchor_ids: List[str] = Field(default_factory=list)
    grounding_passed: bool = False
    keyword_anchor_coverage: float = 0.0
    section_coverage_given: float = 0.0
    section_coverage_when: float = 0.0
    section_coverage_then: float = 0.0
    readability_passed: bool = True
    forbidden_pipeline_terms: List[str] = Field(default_factory=list)
    max_step_length: int = 180
    overlong_step_numbers: List[int] = Field(default_factory=list)
    full_pre_audit_passed: bool = False


class TestScenarioA6(_PromptOutputBase):
    scenario_id: str
    scenario_name: str
    scenario_type: str  # happy_path | negative_path | validation_path | navigation_path | recovery_path | registration_path | access_control_path | data_entry_path | unknown_path
    source_intent_id: str
    source_flow_id: str
    source_flow_name: str
    source_flow_type: str  # single_step_outcome | ordered_sequence | branching_flow
    source_screen_intent_id: Optional[str] = None
    source_group_id: Optional[str] = None
    source_transition_ids: List[str] = Field(default_factory=list)
    source_transition_indexes: List[int] = Field(default_factory=list)
    user_actions: List[str] = Field(default_factory=list)
    start_state: str
    end_state: str
    trigger_action: TriggerActionA5
    test_objective: str
    preconditions: List[str] = Field(default_factory=list)
    test_data: List[TestDataA6] = Field(default_factory=list)
    steps: List[TestScenarioStepA6] = Field(default_factory=list)
    expected_results: List[str] = Field(default_factory=list)
    assertions: List[AssertionA6] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: str  # high | medium | low
    source_blueprint_id: Optional[str] = None
    generation_method: Optional[str] = None
    status: Optional[str] = None
    grounding_contract: Optional[GroundingContractA6] = None
    pre_generation_grounding: Optional[PreGenerationGroundingA6] = None


class UnresolvedScenarioItemA6(_PromptOutputBase):
    item_type: str  # invalid_intent | missing_critical_field | unsupported_intent | insufficient_expected_result | insufficient_traceability | insufficient_evidence
    source_intent_id: Optional[str] = None
    source_flow_id: Optional[str] = None
    reason: str


class CoverageMatrixItemA6(_PromptOutputBase):
    intent_id: str
    scenario_id: Optional[str] = None
    coverage_status: str  # covered | unresolved
    reason: str


class ScenarioGenerationSummaryA6(_PromptOutputBase):
    total_behaviour_intents: int = 0
    total_test_scenarios: int = 0
    total_unresolved_scenario_items: int = 0
    coverage_rate: float = 0.0


class ScenarioGenerationMetricsA6(_PromptOutputBase):
    blueprint_count: int = 0
    llm_generated_count: int = 0
    llm_repaired_count: int = 0
    llm_readability_repair_count: int = 0
    unresolved_count: int = 0
    deterministic_fallback_count: int = 0
    required_anchor_count: int = 0
    matched_anchor_count: int = 0
    anchor_coverage_rate: float = 0.0
    given_anchor_coverage: float = 0.0
    when_anchor_coverage: float = 0.0
    then_anchor_coverage: float = 0.0
    unexpected_placeholder_count: int = 0
    invalid_trace_ref_count: int = 0
    _section_count: int = 0
    _given_sum: float = 0.0
    _when_sum: float = 0.0
    _then_sum: float = 0.0


class BDDScenarioGenerationResult(_PromptOutputBase):
    test_scenarios: List[TestScenarioA6] = Field(default_factory=list)
    unresolved_scenario_items: List[UnresolvedScenarioItemA6] = Field(default_factory=list)
    coverage_matrix: List[CoverageMatrixItemA6] = Field(default_factory=list)
    generation_summary: ScenarioGenerationSummaryA6
    scenario_writing_blueprints: List[ScenarioWritingBlueprint] = Field(default_factory=list)
    scenario_generation_metrics: ScenarioGenerationMetricsA6 = Field(default_factory=ScenarioGenerationMetricsA6)


# ──────────────────────────────────────────────
# A7: Scenario evidence audit (prompt: prompt_scenario_evidence_audit; shares shape with legacy validation)
# ──────────────────────────────────────────────

class StepAuditSupportingEvidenceA7(_PromptOutputBase):
    state_ids: List[str] = Field(default_factory=list)
    transition_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)


class StepAuditIssueA7(_PromptOutputBase):
    issue_type: str
    issue_description: str


class StepAuditA7(_PromptOutputBase):
    step_number: int
    keyword: str
    step_text: str
    status: Optional[str] = None  # Added to support compact format "ok"
    grounding_level: Optional[str] = None
    step_support_status: Optional[str] = None
    step_grounding_value: Optional[float] = None
    audit_reason: Optional[str] = None
    supporting_evidence: Optional[Union[StepAuditSupportingEvidenceA7, str]] = None
    audit_issues: List[StepAuditIssueA7] = Field(default_factory=list)


class ScenarioAcceptanceDecisionA7(_PromptOutputBase):
    include_in_final_output: bool
    reason: str


class ValidationScoresA7(_PromptOutputBase):
    intent_alignment_score: float = 0.0
    screen_intent_grounding_score: float = 0.0
    flow_grounding_score: float = 0.0
    evidence_grounding_score: float = 0.0
    bdd_structure_score: float = 0.0
    data_and_assertion_quality_score: float = 0.0
    hallucination_penalty: float = 0.0


class RevisionSuggestionA7(_PromptOutputBase):
    target: str  # scenario | step_number
    issue_type: str
    suggestion: str


class HallucinationFlagsA7(_PromptOutputBase):
    element_hallucination: bool = False
    business_rule_hallucination: bool = False
    data_hallucination: bool = False
    outcome_hallucination: bool = False
    transition_hallucination: bool = False
    bdd_structure_issue: bool = False


class ValidatedScenarioA7(_PromptOutputBase):
    scenario_id: str
    source_flow_id: str
    source_intent_id: str
    scenario_name: str
    scenario_type: str
    validation_status: str  # validated | low_confidence | needs_revision | rejected
    final_reliability: float
    scores: ValidationScoresA7
    step_audits: List[StepAuditA7] = Field(default_factory=list)
    hallucination_flags: HallucinationFlagsA7
    revision_suggestions: List[RevisionSuggestionA7] = Field(default_factory=list)
    acceptance_decision: ScenarioAcceptanceDecisionA7
    validation_warnings: List[str] = Field(default_factory=list)


class FinalOutputSummaryA7(_PromptOutputBase):
    validated_count: int = 0
    rejected_count: int = 0
    low_confidence_count: int = 0
    needs_revision_count: int = 0
    total_count: int = 0


class ScenarioValidationResult(_PromptOutputBase):
    validated_scenarios: List[ValidatedScenarioA7] = Field(default_factory=list)
    final_output_summary: FinalOutputSummaryA7
    package_warnings: List[str] = Field(default_factory=list)

