from __future__ import annotations
from typing import List, Optional, Dict, Any, Union, Type
from pydantic import BaseModel, Field


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
# A1: UI State Extraction (ui_state_extraction.txt)
# ──────────────────────────────────────────────

class UIElementA1(_PromptOutputBase):
    element_id: str
    type: str
    label: Optional[str] = None
    text: Optional[str] = None
    placeholder: Optional[str] = None
    bbox: List[float] = Field(min_length=4, max_length=4)
    actionable: bool = False
    is_feedback: bool = False
    semantic_role: Optional[str] = None
    visibility: str = "fully_visible"


class UIStateA1(_PromptOutputBase):
    state_id: str
    image_id: str
    page_type: str
    state_summary: str
    state_signature: str
    ui_elements: List[UIElementA1] = Field(default_factory=list)
    has_form: bool = False
    has_table: bool = False
    has_modal: bool = False
    has_feedback: bool = False


class UIStateExtractionResult(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    ui_state_package_id: str
    run_id: str
    extracted_states: List[UIStateA1] = Field(default_factory=list)
    extraction_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A2: Semantic Canonicalization (semantic_canonicalization.txt)
# ──────────────────────────────────────────────

class CanonicalElementA2(_PromptOutputBase):
    canonical_element_id: str
    source_element_refs: List[SourceElementRefA2] = Field(default_factory=list)
    type: str
    label: Optional[str] = None
    text: Optional[str] = None
    actionable: bool = True
    is_feedback: bool = False
    semantic_role: Optional[str] = None


class CanonicalFeedbackElementA2(_PromptOutputBase):
    canonical_element_id: str
    source_element_refs: List[SourceElementRefA2] = Field(default_factory=list)
    feedback_type: str
    text: Optional[str] = None


class PrimaryActionCandidateA2(_PromptOutputBase):
    canonical_element_id: str
    action_type: str
    action_label: str


class PreservedDistinctionA2(_PromptOutputBase):
    distinction_type: str
    state_ids: List[str] = Field(default_factory=list)
    reason: str


class ExcludedStateA2(_PromptOutputBase):
    state_id: str
    reason: str


class CanonicalStateA2(_PromptOutputBase):
    canonical_state_id: str
    representative_state_id: str
    member_state_ids: List[str] = Field(default_factory=list)
    source_image_ids: List[str] = Field(default_factory=list)
    canonical_page_type: str
    canonical_summary: str
    canonical_elements: List[CanonicalElementA2] = Field(default_factory=list)
    canonical_feedback_elements: List[CanonicalFeedbackElementA2] = Field(default_factory=list)
    primary_action_candidates: List[PrimaryActionCandidateA2] = Field(default_factory=list)
    preserved_distinctions: List[PreservedDistinctionA2] = Field(default_factory=list)
    merge_rationale: str = ""


class MergeDecisionA2(_PromptOutputBase):
    decision_id: str
    state_ids: List[str] = Field(default_factory=list)
    decision: str  # merged|kept_separate
    reason: str = ""
    supporting_element_refs: List[SourceElementRefA2] = Field(default_factory=list)


class SemanticCanonicalizationResult(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    canonical_state_set_id: str
    source_ui_state_package_id: Optional[str] = None
    canonical_states: List[CanonicalStateA2] = Field(default_factory=list)
    non_merged_state_ids: List[str] = Field(default_factory=list)
    excluded_state_ids: List[ExcludedStateA2] = Field(default_factory=list)
    merge_decisions: List[MergeDecisionA2] = Field(default_factory=list)
    canonicalization_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A3: UI Flow Discovery (llm_flow_discovery.txt)
# ──────────────────────────────────────────────

class FlowTransitionTriggerA3(_PromptOutputBase):
    trigger_element_id: str
    action_type: str
    action_label: str
    trigger_text: Optional[str] = None
    trigger_semantic_role: Optional[str] = None


class TargetStateEvidenceA3(_PromptOutputBase):
    target_page_type: str
    supporting_element_ids: List[str] = Field(default_factory=list)
    supporting_feedback_element_ids: List[str] = Field(default_factory=list)
    reason: str


class FlowTransitionA3(_PromptOutputBase):
    transition_id: str
    from_state_id: str
    to_state_id: str
    trigger: FlowTransitionTriggerA3
    target_state_evidence: TargetStateEvidenceA3
    transition_basis: List[str] = Field(default_factory=list)
    ordering_strength: str  # strong, medium, weak, none
    transition_certainty: str  # likely, plausible, uncertain, unsupported
    uncertainty_reason: Optional[str] = None


class FlowStateInSequenceA3(_PromptOutputBase):
    sequence_index: int
    canonical_state_id: str
    state_role_in_flow: str  # entry, intermediate, terminal_candidate, standalone, cluster_member
    page_type: str
    state_summary: str
    evidence_element_ids: List[str] = Field(default_factory=list)


class FlowCompletenessA3(_PromptOutputBase):
    has_entry_state: bool
    has_action_transition: bool
    has_observable_terminal_state: bool
    missing_intermediate_state: bool
    missing_final_verification: bool


class IntentReadinessA3(_PromptOutputBase):
    readiness_level: str  # ready_for_intent, partial_intent_only, capability_only, not_ready
    reason: str
    usable_for_primary_scenario: bool


class FlowEvidencePackageA3(_PromptOutputBase):
    state_ids: List[str] = Field(default_factory=list)
    transition_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)
    feedback_element_ids: List[str] = Field(default_factory=list)


class FlowDiscoveryA3(_PromptOutputBase):
    flow_id: str
    flow_label: str
    flow_type: str  # ordered_sequence, semantic_cluster, single_state_inferred_flow
    flow_summary: str
    state_sequence: List[FlowStateInSequenceA3] = Field(default_factory=list)
    transitions: List[FlowTransitionA3] = Field(default_factory=list)
    flow_completeness: FlowCompletenessA3
    intent_readiness: IntentReadinessA3
    flow_evidence_package: FlowEvidencePackageA3
    flow_warnings: List[str] = Field(default_factory=list)


class UIFlowDiscoveryResult(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    flow_discovery_result_id: str
    source_canonical_state_set_id: str
    flows: List[FlowDiscoveryA3] = Field(default_factory=list)
    unassigned_state_ids: List[str] = Field(default_factory=list)
    discovery_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A5: Behaviour Intent (behaviour_intent.txt)
# ──────────────────────────────────────────────

class ObservablePreconditionA5(_PromptOutputBase):
    description: str = ""
    state_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)
    source_flow_fields: List[str] = Field(default_factory=list)


class MainUserActionA5(_PromptOutputBase):
    description: str = ""
    transition_ids: List[str] = Field(default_factory=list)
    state_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)
    action_type: str
    source_flow_fields: List[str] = Field(default_factory=list)


class ObservableResultA5(_PromptOutputBase):
    description: str = ""
    state_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)
    feedback_element_ids: List[str] = Field(default_factory=list)
    source_flow_fields: List[str] = Field(default_factory=list)


class IntentGroundingEvidenceA5(_PromptOutputBase):
    flow_id: str
    state_ids: List[str] = Field(default_factory=list)
    transition_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)
    feedback_element_ids: List[str] = Field(default_factory=list)
    ordering_strength_used: List[str] = Field(default_factory=list)
    flow_completeness_used: Dict[str, bool] = Field(default_factory=dict)


class IntentAmbiguityA5(_PromptOutputBase):
    is_ambiguous: bool = False
    ambiguity_reasons: List[str] = Field(default_factory=list)


class BehaviourIntentPrimaryA5(_PromptOutputBase):
    intent_id: str
    intent_name: str
    domain: str
    intent_scope: str  # end_to_end, partial_flow, single_state_capability, alternative_path, validation_error, unknown_behaviour
    user_goal: str
    behaviour_outcome: str  # success_observed, failure_observed, validation_error_observed, no_result_observed, in_progress, capability_only, unknown
    outcome_certainty: str  # grounded, partially_inferred, inferred_only, unknown
    observable_precondition: ObservablePreconditionA5
    main_user_action: MainUserActionA5
    observable_result: ObservableResultA5
    grounding_evidence: IntentGroundingEvidenceA5
    grounding_level: str
    ambiguity: IntentAmbiguityA5
    intent_warnings: List[str] = Field(default_factory=list)


class BehaviourIntentAlternativeA5(_PromptOutputBase):
    intent_id: str
    intent_name: str
    domain: str
    intent_scope: str
    user_goal: str
    behaviour_outcome: str
    outcome_certainty: str
    grounding_evidence: IntentGroundingEvidenceA5
    grounding_level: str
    ambiguity: IntentAmbiguityA5
    intent_warnings: List[str] = Field(default_factory=list)


class FlowIntentA5(_PromptOutputBase):
    flow_id: str
    source_flow_type: str
    primary_intent: BehaviourIntentPrimaryA5
    alternative_intents: List[BehaviourIntentAlternativeA5] = Field(default_factory=list)


class BehaviourIntentInferenceResult(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    intent_package_id: str
    source_flow_discovery_result_id: str
    flow_intents: List[FlowIntentA5] = Field(default_factory=list)
    package_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A6: BDD Scenario Generation (scenario_generation.txt)
# ──────────────────────────────────────────────

class BDDStepA6(_PromptOutputBase):
    step_id: str
    keyword: str
    text: str
    evidence_state_ids: List[str] = Field(default_factory=list)
    evidence_transition_ids: List[str] = Field(default_factory=list)
    evidence_element_ids: List[str] = Field(default_factory=list)
    source_intent_field: str
    inference_level: str


class ScenarioA6(_PromptOutputBase):
    scenario_id: str
    linked_flow_id: str
    linked_intent_ids: List[str] = Field(default_factory=list)
    scenario_type: str
    scenario_title: str
    bdd_steps: List[BDDStepA6] = Field(default_factory=list)
    gherkin_text: str
    generation_warnings: List[str] = Field(default_factory=list)


class FeatureA6(_PromptOutputBase):
    feature_id: str
    feature_name: str
    source_domain: str
    scenarios: List[ScenarioA6] = Field(default_factory=list)


class SkippedIntentA6(_PromptOutputBase):
    flow_id: str
    intent_id: str
    reason: str


class BDDScenarioGenerationResult(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    scenario_draft_package_id: str
    source_intent_package_id: str
    features: List[FeatureA6] = Field(default_factory=list)
    skipped_intents: List[SkippedIntentA6] = Field(default_factory=list)
    package_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A7: Scenario Validation (scenario_validation.txt)
# ──────────────────────────────────────────────

class StepAuditSupportingEvidenceA7(_PromptOutputBase):
    state_ids: List[str] = Field(default_factory=list)
    transition_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)


class StepAuditA7(_PromptOutputBase):
    step_id: str
    is_grounded: bool
    grounding_score: float
    hallucination_detected: bool
    hallucination_reason: Optional[str] = None
    supporting_evidence: StepAuditSupportingEvidenceA7


class ScenarioAcceptanceDecisionA7(_PromptOutputBase):
    include_in_final_output: bool
    reason: str
    suggested_priority: str


class ValidationScoresA7(_PromptOutputBase):
    grounding_score: float
    evidence_coverage_score: float
    logic_consistency_score: float
    overall_reliability: float


class RevisionSuggestionA7(_PromptOutputBase):
    step_id: Optional[str] = None
    original_text: str
    suggested_text: str
    reason: str


class HallucinationFlagsA7(_PromptOutputBase):
    has_hallucination: bool = False
    hallucination_types: List[str] = Field(default_factory=list)
    affected_step_ids: List[str] = Field(default_factory=list)
    reason: str = ""


class ValidatedScenarioA7(_PromptOutputBase):
    scenario_id: str
    validation_status: str  # validated, rejected, needs_revision
    grounding_score: float
    evidence_coverage_score: float
    final_reliability: float
    step_audits: List[StepAuditA7] = Field(default_factory=list)
    scores: ValidationScoresA7
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
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    validated_scenario_package_id: str
    source_scenario_draft_package_id: str
    validated_scenarios: List[ValidatedScenarioA7] = Field(default_factory=list)
    final_output_summary: FinalOutputSummaryA7
    package_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Registry & Helper
# ──────────────────────────────────────────────

SCHEMA_REGISTRY: Dict[str, Type[BaseModel]] = {
    "ui_state_extraction": UIStateExtractionResult,
    "semantic_canonicalization": SemanticCanonicalizationResult,
    "ui_flow_discovery": UIFlowDiscoveryResult,
    "behaviour_intent_inference": BehaviourIntentInferenceResult,
    "behaviour_scenario_generation": BDDScenarioGenerationResult,
    "scenario_validation": ScenarioValidationResult,
}


def get_schema(name: str) -> Type[BaseModel]:
    """Look up a schema class by name."""
    if name not in SCHEMA_REGISTRY:
        raise ValueError(f"Schema '{name}' not found in SCHEMA_REGISTRY.")
    return SCHEMA_REGISTRY[name]
