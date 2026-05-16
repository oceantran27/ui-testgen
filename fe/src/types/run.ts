/** Types aligned with `be/app/api/routes/runs.py` JSON (snake_case). */

export type RunConfig = {
  max_revision_round?: number;
  allow_unordered_images?: boolean;
  allow_duplicate_images?: boolean;
  input_level_mode?: string;
};

export type RunResponse = {
  run_id: string;
  project_name?: string | null;
  description?: string | null;
  status: string;
  total_images?: number;
  valid_images?: number;
  invalid_images?: number;
  config?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
  submitted_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  current_phase?: string | null;
  current_node?: string | null;
  progress_percentage?: number | null;
  graph_status?: string | null;
};

export type RunListResponse = {
  runs: RunResponse[];
  total: number;
};

export type RunCreateBody = {
  project_name?: string | null;
  description?: string | null;
  config?: RunConfig | null;
};

export type RunSubmitResponse = {
  run_id: string;
  status: string;
  job_id?: string | null;
  message: string;
};

export type RunCancelResponse = {
  run_id: string;
  status: string;
  message: string;
};

export type PipelineLogResponse = {
  run_id: string;
  content?: string | null;
  path?: string | null;
  message?: string | null;
  next_byte?: number;
};

export type ImageUploadItem = {
  image_id?: string | null;
  original_filename: string;
  format?: string | null;
  file_size?: number | null;
  storage_uri?: string | null;
  upload_status: string;
  error_message?: string | null;
};

export type UploadImagesResponse = {
  run_id: string;
  uploaded_count?: number;
  failed_count?: number;
  image_items?: ImageUploadItem[];
  warnings?: string[];
};

export type ImageRecord = {
  image_id: string;
  original_filename: string;
  format?: string | null;
  file_size?: number | null;
  width?: number | null;
  height?: number | null;
  upload_order?: number | null;
  storage_uri?: string | null;
  quality_status?: string | null;
  sha256_hash?: string | null;
  created_at?: string | null;
};

export type ImageListResponse = {
  run_id: string;
  total: number;
  images: ImageRecord[];
};

export type GraphStatusResponse = {
  run_id: string;
  graph_status?: string | null;
  current_phase?: string | null;
  current_node?: string | null;
  progress_percentage?: number | null;
  graph_thread_id?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type ArtifactsResponse = {
  run_id: string;
  total: number;
  artifacts: Array<{
    artifact_id: string;
    type: string;
    node_name?: string | null;
    storage_uri?: string | null;
    created_at?: string | null;
  }>;
};

export type ModelCallSummary = {
  model_call_id: string;
  node_name?: string | null;
  task_name?: string | null;
  provider?: string | null;
  model_name?: string | null;
  request_type?: string | null;
  status?: string | null;
  latency_ms?: number | null;
  token_usage?: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
  };
  image_count?: number | null;
  retry_count?: number | null;
  error_code?: string | null;
  created_at?: string | null;
};

export type ModelCallsListResponse = {
  run_id: string;
  total: number;
  model_calls: ModelCallSummary[];
};

export type ModelCallDetailResponse = ModelCallSummary & {
  job_id?: string | null;
  error_message?: string | null;
  raw_output_artifact_id?: string | null;
};

export type PipelinePhaseModelKey =
  | "ui_state_extraction"
  | "screen_intent_extraction"
  | "flow_context_builder"
  | "intent_aware_flow_discovery"
  | "behaviour_contract_builder"
  | "bdd_scenario_generation"
  | "scenario_evidence_audit";

export type ModelConfigResponse = {
  run_id: string;
  default_model_provider?: string;
  gemini_text_model?: string;
  gemini_vision_model?: string;
  openai_text_model?: string;
  openai_vision_model?: string;
  pipeline_phase_models?: Partial<
    Record<PipelinePhaseModelKey, { provider: string; model: string }>
  >;
  feature_flags?: Record<string, boolean>;
  retry_config?: Record<string, number>;
  mock_mode?: boolean;
};

// ──────────────────────────────────────────────
// Agent-Specific Packages (aligned with schemas.py)
// ──────────────────────────────────────────────

export type UIStateSummary = {
  state_id: string;
  image_id: string;
  page_type?: string | null;
  screen_type?: string | null;
  screen_purpose?: string | null;
  domain?: string | null;
  state_summary?: string | null;
  state_signature?: string | null;
  confidence?: number | null;
  has_form?: boolean;
  has_table?: boolean;
  has_modal?: boolean;
  has_feedback?: boolean;
  extraction_status?: string | null;
  created_at?: string | null;
};

export type UIStatesListResponse = {
  run_id: string;
  total: number;
  states: UIStateSummary[];
};

export type UIElementRecord = {
  element_id: string;
  type: string;
  label?: string | null;
  text?: string[] | string | null;
  bbox?: number[] | null;
  actionable: boolean;
  is_feedback: boolean;
  feedback_type?: string | null;
  action_type?: string | null;
  semantic_role?: string | null;
  visibility?: string | null;
  interaction_group_id?: string | null;
};

export type InteractionGroupRecord = {
  group_id: string;
  group_name: string;
  purpose: string;
  element_ids: string[];
};

export type ScreenBehaviourIntentRecord = {
  intent_id: string;
  state_id: string;
  intent_name: string;
  user_goal: string;
  business_value: string;
  interaction_group_ids: string[];
  intent_type: string;
};

export type UIStateDetailResponse = UIStateSummary & {
  ui_elements: UIElementRecord[];
  interaction_groups?: InteractionGroupRecord[];
  screen_intents?: ScreenBehaviourIntentRecord[];
  feedback_elements: unknown[];
  primary_action_candidates: unknown[];
};


export type FlowTransitionTrigger = {
  action_type: string;
  text: string[];
};

export type FlowTransition = {
  transition_id: string;
  from_state_id: string;
  to_state_id: string;
  transition_type: string;
  trigger: FlowTransitionTrigger;
  target_state_evidence?: {
    target_page_type?: string;
    supporting_element_ids?: string[];
    supporting_feedback_element_ids?: string[];
    reason?: string;
  } | null;
  transition_basis: string[];
  ordering_strength: string;
  transition_certainty?: string | null;
  uncertainty_reason?: string | null;
  reason?: string | null;
  confidence_label?: string | null;
  score?: number | null;
};

export type IntentReadiness = {
  readiness_level: string;
  reason: string;
  usable_for_primary_scenario: boolean;
};

export type FlowEvidencePackage = {
  state_ids: string[];
  transition_ids: string[];
  element_ids: string[];
  feedback_element_ids: string[];
};

export type FlowSummary = {
  flow_id: string;
  flow_label: string;
  flow_type: string;
  entry_state_id?: string | null;
  state_ids: string[];
  terminal_state_ids: string[];
  state_sequence?: Array<{
    sequence_index: number;
    canonical_state_id: string;
    state_role_in_flow: string;
    page_type: string;
    state_summary: string;
    evidence_element_ids: string[];
    intent_id?: string;
  }>;
  flow_completeness?: Record<string, boolean>;
  intent_readiness?: IntentReadiness;
  flow_evidence_package?: FlowEvidencePackage;
};

export type FlowStateCardRecord = {
  card_id: string;
  state_id: string;
  page_type: string;
  state_summary: string;
  local_intents: ScreenBehaviourIntentRecord[];
  interaction_catalog: {
    groups: InteractionGroupRecord[];
    standalone_elements: UIElementRecord[];
  };
};

export type FlowsListResponse = {
  run_id: string;
  total: number;
  flows: FlowSummary[];
};

export type FlowDetailResponse = FlowSummary & {
  transitions: FlowTransition[];
};

export type BehaviourIntentSummary = {
  intent_id: string;
  flow_id: string;
  behaviour_name: string;
  intent_type: string;
  test_path: string;
  user_intent: string;
  business_goal: string;
  start_state: string;
  end_state: string;
  confidence: "high" | "medium" | "low" | string;
  created_at?: string | null;
};

export type BehaviourIntentsListResponse = {
  run_id: string;
  total: number;
  intents: BehaviourIntentSummary[];
};

export type ScenarioSummary = {
  scenario_id: string;
  title: string;
  scenario_type: string;
  status: string;
  validation_status?: string | null;
  /** From list endpoint: maps from initial_confidence */
  confidence?: number | null;
  confidence_label?: string | null;
  grounding_mode?: string | null;
};

export type ScenariosListResponse = {
  run_id: string;
  total: number;
  scenarios: ScenarioSummary[];
};

export type BddStepRecord = {
  step_number: number;
  keyword: string;
  text: string;
  source: string;
};

export type ValidationScores = {
  grounding_score: number;
  screen_intent_grounding_score?: number | null;
  evidence_coverage_score: number;
  transition_support_score?: number | null;
  bdd_structure_score: number;
  hallucination_penalty: number;
};

export type StepAuditSupportingEvidence = {
  state_ids?: string[];
  transition_ids?: string[];
  element_ids?: string[];
};

export type StepAuditRecord = {
  step_number: number;
  keyword: string;
  step_text: string;
  grounding_level: string;
  step_support_status: string;
  step_grounding_value: number;
  audit_reason: string;
  supporting_evidence: StepAuditSupportingEvidence;
  audit_issues?: Array<{ issue_type: string; issue_description: string }>;
};

export type HallucinationFlagsRecord = {
  element_hallucination?: boolean;
  business_rule_hallucination?: boolean;
  data_hallucination?: boolean;
  outcome_hallucination?: boolean;
  transition_hallucination?: boolean;
  bdd_structure_issue?: boolean;
};

export type RevisionSuggestionRecord = {
  target: string;
  issue_type: string;
  suggestion: string;
};

export type ScenarioDetailResponse = {
  scenario_id: string;
  run_id?: string;
  intent_id?: string | null;
  flow_id?: string | null;
  feature?: string | null;
  scenario_title: string;
  scenario_type: string;
  gherkin_text: string;
  bdd_steps: BddStepRecord[];
  status?: string;
  validation?: {
    validation_status: string;
    final_reliability: number;
    hallucination_flags?: HallucinationFlagsRecord | Record<string, boolean>;
    acceptance_decision?: {
      include_in_final_output: boolean;
      reason: string;
    };
    scores?: ValidationScores;
    validated_at?: string | null;
  };
};

export type ValidatedScenarioRecord = {
  scenario_id: string;
  source_flow_id?: string;
  source_intent_id?: string;
  scenario_name?: string;
  scenario_type?: string;
  validation_status: string;
  final_reliability: number;
  scores?: ValidationScores;
  step_audits?: StepAuditRecord[];
  hallucination_flags?: HallucinationFlagsRecord;
  revision_suggestions?: RevisionSuggestionRecord[];
  acceptance_decision: {
    include_in_final_output: boolean;
    reason: string;
  };
  validation_warnings?: string[];
};

export type ScenarioValidationResult = {
  validated_scenarios: ValidatedScenarioRecord[];
  /** Agent 7 summary counts (snake_case from backend model_dump). */
  final_output_summary?: {
    validated_count?: number;
    rejected_count?: number;
    low_confidence_count?: number;
    needs_revision_count?: number;
    total_count?: number;
  };
  package_warnings?: string[];
};
