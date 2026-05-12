"""
Schema Registry — Pydantic v2 output schemas aligned with be/app/prompts/*.txt §4 Output Format.

Envelope fields (schema_version, agent_name) may appear in model JSON; extra keys are ignored.
Inter-agent payloads:
  A1 → single UIStateExtractionResult per image; wrap into UIStatePackage (extracted_states[]) for A2.
  A2 → SemanticCanonicalizationResult → A3 input (canonical_states subset).
  A3 → UIFlowDiscoveryResult → A4 with canonical_state_image_lookup.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict, Field


class _PromptOutputBase(BaseModel):
    model_config = ConfigDict(extra="ignore")


# ──────────────────────────────────────────────
# Common
# ──────────────────────────────────────────────


class VisualDeltaRef(BaseModel):
    """Reference to a field on transition visual_delta (used in A5, A6, A7)."""

    model_config = ConfigDict(extra="ignore")
    transition_id: str
    delta_field: str


# ──────────────────────────────────────────────
# A1: UI State Extraction Agent (ui_state_extraction.txt)
# ──────────────────────────────────────────────


class VisibleTextA1(_PromptOutputBase):
    text_id: str
    text: str
    bbox: List[int] = Field(min_length=4, max_length=4)
    readability: str  # clear|partial|illegible


class UIElementA1(_PromptOutputBase):
    element_id: str
    type: str
    label: Optional[str] = None
    text: Optional[str] = None
    bbox: List[int] = Field(min_length=4, max_length=4)
    actionable: bool
    is_feedback: bool
    semantic_role: Optional[str] = None
    visibility: str = "fully_visible"


class FeedbackElementA1(_PromptOutputBase):
    """Per prompt: no bbox on feedback row (references ui_elements by element_id)."""

    element_id: str
    feedback_type: str
    text: Optional[str] = None


class PrimaryActionCandidateA1(_PromptOutputBase):
    element_id: str
    action_type: str
    action_label: str


class StateQualityA1(_PromptOutputBase):
    visual_readability: str  # high|medium|low
    extraction_completeness: str  # complete|partial|poor
    warnings: List[str] = Field(default_factory=list)


class UIStateExtractionResult(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    extraction_status: str = "success"  # success|partial|failed
    state_id: str
    source_image_id: str
    page_type: str
    state_summary: str
    visible_texts: List[VisibleTextA1] = Field(default_factory=list)
    ui_elements: List[UIElementA1] = Field(default_factory=list)
    feedback_elements: List[FeedbackElementA1] = Field(default_factory=list)
    primary_action_candidates: List[PrimaryActionCandidateA1] = Field(default_factory=list)
    state_quality: StateQualityA1


# Built in code for semantic_duplicate input (not an LLM output schema).
class UIStatePackage(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    ui_state_package_id: str
    extracted_states: List[Dict[str, Any]]  # loose: mirrors prompt examples + DB ids


# ──────────────────────────────────────────────
# A2: Semantic Canonicalization (semantic_duplicate.txt)
# ──────────────────────────────────────────────


class SourceElementRefA2(_PromptOutputBase):
    state_id: str
    element_id: str


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


class TransitionEvidenceRefA3(_PromptOutputBase):
    canonical_state_id: str
    canonical_element_id: str
    evidence_role: str


class FlowTransitionA3(_PromptOutputBase):
    transition_id: str
    from_state_id: str
    to_state_id: str
    trigger_element_id: Optional[str] = None
    action_type: str
    transition_basis: str
    ordering_strength: str
    supporting_evidence_refs: List[TransitionEvidenceRefA3] = Field(default_factory=list)
    uncertainty_reason: Optional[str] = None


class FlowCompletenessA3(_PromptOutputBase):
    has_entry_state: bool
    has_terminal_state: bool
    missing_intermediate_state: bool
    missing_final_verification: bool
    has_supported_transitions: bool = False


class FlowDiscoveryA3(_PromptOutputBase):
    flow_id: str
    flow_type: str
    flow_label: str
    entry_state_id: Optional[str] = None
    state_ids: List[str] = Field(default_factory=list)
    terminal_state_ids: List[str] = Field(default_factory=list)
    transitions: List[FlowTransitionA3] = Field(default_factory=list)
    flow_completeness: FlowCompletenessA3
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
# A4: Transition Visual Validation (transition_visual_validation.txt)
# ──────────────────────────────────────────────


class VisualDeltaItemA4(_PromptOutputBase):
    description: str
    visual_region: List[int] = Field(min_length=4, max_length=4)
    evidence_type: str


class VisualDeltaDetailA4(_PromptOutputBase):
    page_identity_change: Optional[str] = None
    added_elements: List[VisualDeltaItemA4] = Field(default_factory=list)
    removed_elements: List[VisualDeltaItemA4] = Field(default_factory=list)
    changed_elements: List[VisualDeltaItemA4] = Field(default_factory=list)
    feedback_added: List[VisualDeltaItemA4] = Field(default_factory=list)
    status_changes: List[VisualDeltaItemA4] = Field(default_factory=list)
    unchanged_key_regions: List[VisualDeltaItemA4] = Field(default_factory=list)


class ValidationInputRefsA4(_PromptOutputBase):
    from_image_ids: List[str] = Field(default_factory=list)
    to_image_ids: List[str] = Field(default_factory=list)


class ValidatedTransitionA4(_PromptOutputBase):
    transition_id: str
    from_state_id: str
    to_state_id: str
    trigger_element_id: Optional[str] = None
    action_type: str
    transition_basis: str = ""
    ordering_strength: str = ""
    validation_input_refs: ValidationInputRefsA4 = Field(default_factory=ValidationInputRefsA4)
    image_usability: str = "usable"
    visual_delta: VisualDeltaDetailA4
    transition_support: str
    visual_support_score: Optional[float] = None
    support_reason: str = ""
    validation_flags: List[str] = Field(default_factory=list)


class ValidatedFlowA4(_PromptOutputBase):
    flow_id: str
    flow_type: str
    flow_label: str = ""
    entry_state_id: Optional[str] = None
    state_ids: List[str] = Field(default_factory=list)
    terminal_state_ids: List[str] = Field(default_factory=list)
    transitions: List[ValidatedTransitionA4] = Field(default_factory=list)
    flow_validation_status: str
    flow_visual_support_score: Optional[float] = None
    flow_validation_warnings: List[str] = Field(default_factory=list)


class TransitionVisualValidationResult(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    validated_flow_package_id: str
    source_flow_discovery_result_id: str
    validated_flows: List[ValidatedFlowA4] = Field(default_factory=list)
    package_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A5: Behaviour Intent (behaviour_intent.txt)
# ──────────────────────────────────────────────


class IntentEvidenceRefA5(_PromptOutputBase):
    ref_type: str
    state_id: Optional[str] = None
    transition_id: Optional[str] = None
    element_id: Optional[str] = None
    description: str = ""


class ObservablePreconditionA5(_PromptOutputBase):
    state_ids: List[str] = Field(default_factory=list)
    description: str = ""
    evidence_refs: List[IntentEvidenceRefA5] = Field(default_factory=list)


class MainUserActionA5(_PromptOutputBase):
    transition_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)
    action_type: str
    description: str = ""
    evidence_refs: List[IntentEvidenceRefA5] = Field(default_factory=list)


class ObservableResultA5(_PromptOutputBase):
    state_ids: List[str] = Field(default_factory=list)
    transition_ids: List[str] = Field(default_factory=list)
    description: str = ""
    result_evidence_type: str
    evidence_refs: List[IntentEvidenceRefA5] = Field(default_factory=list)


class IntentGroundingEvidenceA5(_PromptOutputBase):
    state_ids: List[str] = Field(default_factory=list)
    transition_ids: List[str] = Field(default_factory=list)
    element_ids: List[str] = Field(default_factory=list)
    visual_delta_refs: List[VisualDeltaRef] = Field(default_factory=list)
    validation_flags: List[str] = Field(default_factory=list)
    flow_validation_status: str = ""
    flow_visual_support_score: Optional[float] = None


class IntentAmbiguityA5(_PromptOutputBase):
    is_ambiguous: bool = False
    ambiguity_reasons: List[str] = Field(default_factory=list)


class BehaviourIntentPrimaryA5(_PromptOutputBase):
    intent_id: str
    intent_name: str
    domain: str
    intent_scope: str
    user_goal: str
    behaviour_outcome: str
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
    grounding_evidence: IntentGroundingEvidenceA5
    grounding_level: str
    ambiguity: IntentAmbiguityA5
    intent_warnings: List[str] = Field(default_factory=list)


class FlowIntentA5(_PromptOutputBase):
    flow_id: str
    primary_intent: BehaviourIntentPrimaryA5
    alternative_intents: List[BehaviourIntentAlternativeA5] = Field(default_factory=list)


class BehaviourIntentInferenceResult(_PromptOutputBase):
    schema_version: Optional[str] = None
    agent_name: Optional[str] = None
    intent_package_id: str
    source_validated_flow_package_id: str
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
    evidence_visual_delta_refs: List[VisualDeltaRef] = Field(default_factory=list)
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
    visual_delta_refs: List[VisualDeltaRef] = Field(default_factory=list)


class StepAuditIssueA7(_PromptOutputBase):
    issue_type: str
    description: str


class StepAuditA7(_PromptOutputBase):
    step_id: str
    keyword: str
    step_text: str = ""
    source_intent_field: str = ""
    declared_inference_level: str = ""
    step_support_status: str
    grounding_level: str
    step_grounding_value: float = 0.0
    supporting_evidence: StepAuditSupportingEvidenceA7 = Field(
        default_factory=StepAuditSupportingEvidenceA7
    )
    audit_reason: str = ""
    issues: List[StepAuditIssueA7] = Field(default_factory=list)


class HallucinationFlagsA7(_PromptOutputBase):
    element_hallucination: bool = False
    business_rule_hallucination: bool = False
    data_hallucination: bool = False
    outcome_hallucination: bool = False
    transition_hallucination: bool = False
    bdd_structure_issue: bool = False


class RevisionSuggestionA7(_PromptOutputBase):
    target: str
    issue_type: str
    suggestion: str


class AcceptanceDecisionA7(_PromptOutputBase):
    include_in_final_output: bool
    reason: str


class ScenarioValidationScoresA7(_PromptOutputBase):
    """Explicit score fields — OpenAI json_schema strict mode rejects Dict[str, Any]."""

    grounding_score: float = 0.0
    evidence_coverage_score: float = 0.0
    transition_support_score: Optional[float] = None
    bdd_structure_score: float = 0.0
    hallucination_penalty: float = 0.0


class ValidatedScenarioA7(_PromptOutputBase):
    scenario_id: str
    linked_flow_id: str = ""
    linked_intent_ids: List[str] = Field(default_factory=list)
    scenario_title: str = ""
    scenario_type: str = ""
    validation_status: str
    final_reliability: float
    scores: ScenarioValidationScoresA7 = Field(default_factory=ScenarioValidationScoresA7)
    step_audits: List[StepAuditA7] = Field(default_factory=list)
    hallucination_flags: HallucinationFlagsA7
    revision_suggestions: List[RevisionSuggestionA7] = Field(default_factory=list)
    acceptance_decision: AcceptanceDecisionA7


class FinalOutputSummaryA7(_PromptOutputBase):
    validated_count: int = 0
    low_confidence_count: int = 0
    needs_revision_count: int = 0
    rejected_count: int = 0
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
# Registry
# ──────────────────────────────────────────────

SCHEMA_REGISTRY: Dict[str, Type[BaseModel]] = {
    "UIStateExtractionResult": UIStateExtractionResult,
    "SemanticCanonicalizationResult": SemanticCanonicalizationResult,
    "UIFlowDiscoveryResult": UIFlowDiscoveryResult,
    "TransitionVisualValidationResult": TransitionVisualValidationResult,
    "BehaviourIntentInferenceResult": BehaviourIntentInferenceResult,
    "BDDScenarioGenerationResult": BDDScenarioGenerationResult,
    "ScenarioValidationResult": ScenarioValidationResult,
}


def get_schema(name: str) -> Type[BaseModel]:
    if name not in SCHEMA_REGISTRY:
        raise KeyError(f"Schema '{name}' not found. Available: {list(SCHEMA_REGISTRY.keys())}")
    return SCHEMA_REGISTRY[name]
