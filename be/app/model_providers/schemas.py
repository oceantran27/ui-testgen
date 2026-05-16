from __future__ import annotations
from typing import List, Optional, Any, Union
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
# A1: UI State Extraction V2 (prompt: prompt_ui_state_evidence_extraction_v2)
# ──────────────────────────────────────────────


class UIElementA1V2(_PromptOutputBase):
    element_id: str
    element_type: str
    text: List[str] = Field(default_factory=list)
    role_hint: Optional[str] = None
    visual_region: Optional[str] = None


class UIActionA1V2(_PromptOutputBase):
    action_id: str
    action_type: str
    text: List[str] = Field(default_factory=list)
    action_priority: Optional[str] = None
    visual_region: Optional[str] = None


class UIFeedbackA1V2(_PromptOutputBase):
    feedback_id: str
    feedback_type: str
    text: List[str] = Field(default_factory=list)
    related_element_ids: List[str] = Field(default_factory=list)
    visual_region: Optional[str] = None


class InteractionGroupA1V2(_PromptOutputBase):
    group_id: str
    group_type: str
    group_label: Optional[str] = None
    element_ids: List[str] = Field(default_factory=list)
    action_ids: List[str] = Field(default_factory=list)
    feedback_ids: List[str] = Field(default_factory=list)
    primary_action_id: Optional[str] = None
    group_evidence: List[str] = Field(default_factory=list)
    group_confidence: str


class UIStateExtractionV2Result(_PromptOutputBase):
    state_id: str
    screen_purpose: str
    screen_type: str  # form, list, detail, dashboard, search, landing, error, success, modal, unknown
    outcome_state_type: str = "normal"  # normal | validation_error | failure | success | warning | confirmation | review | empty_state | modal | unknown
    domain: str
    visible_elements: List[UIElementA1V2] = Field(default_factory=list)
    available_actions: List[UIActionA1V2] = Field(default_factory=list)
    visible_feedback: List[UIFeedbackA1V2] = Field(default_factory=list)
    interaction_groups: List[InteractionGroupA1V2] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A2 v2: Screen Behaviour Intent Extraction (NEW)
# ──────────────────────────────────────────────


class ScreenIntentPrimaryActionA2(_PromptOutputBase):
    """Primary action for a screen intent — explicit keys for OpenAI strict json_schema."""

    action_id: str
    action_type: str
    text: List[str] = Field(default_factory=list)


class UnresolvedScreenGroupA2(_PromptOutputBase):
    group_id: str
    reason: str


class SelectionOptionA2(_PromptOutputBase):
    option_element_id: str
    option_action_id: Optional[str] = None
    option_text: List[str] = Field(default_factory=list)
    visible_status: str = "unknown"  # selected | unselected | disabled | unknown


class ActionSequenceStepA2(_PromptOutputBase):
    step_type: str  # select_option | click_action | enter_input
    source_action_id: Optional[str] = None
    source_element_id: Optional[str] = None
    text: List[str] = Field(default_factory=list)


class ActionSequenceTemplateA2(_PromptOutputBase):
    sequence_name: str
    steps: List[ActionSequenceStepA2] = Field(default_factory=list)
    outcome_prediction_allowed: bool = False


class ScreenBehaviourIntentA2(_PromptOutputBase):
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
    required_input_groups: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    confidence: str


class ScreenIntentExtractionV2Result(_PromptOutputBase):
    screen_behaviour_intents: List[ScreenBehaviourIntentA2] = Field(default_factory=list)
    unresolved_screen_groups: List[UnresolvedScreenGroupA2] = Field(default_factory=list)



# ──────────────────────────────────────────────
# A3: UI Flow Discovery / intent-aware flows (prompt: prompt_intent_aware_flow_discovery)
# ──────────────────────────────────────────────

class FlowTransitionTriggerA3(_PromptOutputBase):
    action_type: str
    text: List[str] = Field(default_factory=list)





class FlowTransitionA3(_PromptOutputBase):
    from_state: str
    to_state: str
    relation_type: str = "direct_transition"
    trigger_action: FlowTransitionTriggerA3
    source_group_id: Optional[str] = None
    source_screen_intent_id: Optional[str] = None
    evidence_level: str  # strong, medium
    reasoning_pattern: Optional[str] = None
    source_evidence: List[str] = Field(default_factory=list)
    target_evidence: List[str] = Field(default_factory=list)
    source_visible_evidence: List[str] = Field(default_factory=list)
    target_visible_evidence: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class AlternativeOutcomeA3(_PromptOutputBase):
    source_state: str
    source_group_id: Optional[str] = None
    source_screen_intent_id: Optional[str] = None
    trigger_action: FlowTransitionTriggerA3
    outcome_states: List[str] = Field(default_factory=list)
    visible_evidence: List[str] = Field(default_factory=list)
    reason: str
    evidence_level: str
    warnings: List[str] = Field(default_factory=list)


class LocalInteractionA3(_PromptOutputBase):
    source_state: str
    source_group_id: str
    source_screen_intent_id: str
    trigger_action: FlowTransitionTriggerA3
    reason: str


class FlowDiscoveryA3(_PromptOutputBase):
    flow_id: str
    flow_name: str
    flow_type: str  # single_step_outcome, ordered_sequence, branching_flow
    user_goal: str
    ordered_states: List[str] = Field(default_factory=list)
    transitions: List[FlowTransitionA3] = Field(default_factory=list)
    alternative_outcomes: List[AlternativeOutcomeA3] = Field(default_factory=list)
    local_interactions: List[LocalInteractionA3] = Field(default_factory=list)


class SemanticClusterA3(_PromptOutputBase):
    cluster_id: str
    domain: str
    states: List[str] = Field(default_factory=list)
    reason: str


class UncertainRelationA3(_PromptOutputBase):
    state_a: str
    state_b: str
    reason: str


class UIFlowDiscoveryResult(_PromptOutputBase):
    flow_discovery_result_id: Optional[str] = None
    source_canonical_state_set_id: Optional[str] = None
    candidate_flows: List[FlowDiscoveryA3] = Field(default_factory=list)
    semantic_clusters: List[SemanticClusterA3] = Field(default_factory=list)
    uncertain_relations: List[UncertainRelationA3] = Field(default_factory=list)
    discovery_warnings: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# A4–A5: Behaviour contract / intent inference (prompt: prompt_behaviour_contract_builder)
# ──────────────────────────────────────────────

class IntentReadinessA3(_PromptOutputBase):
    readiness_level: str  # ready_for_intent, partial_intent_only, capability_only, not_ready
    reason: str
    usable_for_primary_scenario: bool


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
    total_candidate_flows: int = 0
    total_behaviour_intents: int = 0
    total_unresolved_items: int = 0


class BehaviourIntentInferenceResult(_PromptOutputBase):
    behaviour_intents: List[BehaviourIntentA5] = Field(default_factory=list)
    unresolved_flow_items: List[UnresolvedFlowItemA5] = Field(default_factory=list)
    generation_summary: GenerationSummaryA5


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


class AssertionA6(_PromptOutputBase):
    assertion_type: str  # state_reached | feedback_visible | screen_type_visible | screen_purpose_matched | ui_evidence_present | state_not_reached | feedback_not_visible | unknown
    expected: str
    source: str  # expected_result | expected_ui_evidence | negative_expectation


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


class UnresolvedScenarioItemA6(_PromptOutputBase):
    item_type: str  # invalid_intent | missing_critical_field | unsupported_intent | insufficient_expected_result | insufficient_traceability
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


class BDDScenarioGenerationResult(_PromptOutputBase):
    test_scenarios: List[TestScenarioA6] = Field(default_factory=list)
    unresolved_scenario_items: List[UnresolvedScenarioItemA6] = Field(default_factory=list)
    coverage_matrix: List[CoverageMatrixItemA6] = Field(default_factory=list)
    generation_summary: ScenarioGenerationSummaryA6


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

