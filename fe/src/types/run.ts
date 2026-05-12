/** Types aligned with `be/app/api/routes/runs.py` JSON (snake_case). */

export type RunConfig = {
  max_revision_round?: number;
};

export type RunResponse = {
  run_id: string;
  project_name?: string | null;
  description?: string | null;
  status: string;
  total_images?: number;
  valid_images?: number;
  invalid_images?: number;
  canonical_images?: number;
  duplicate_groups_count?: number;
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
  duplicate_status?: string | null;
  duplicate_group_id?: string | null;
  is_canonical?: boolean | null;
  duplicate_type?: string | null;
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

export type ModelConfigResponse = {
  run_id: string;
  default_model_provider?: string;
  gemini_text_model?: string;
  gemini_vision_model?: string;
  openai_text_model?: string;
  openai_vision_model?: string;
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
  state_summary?: string | null;
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
  text?: string | null;
  bbox: number[];
  actionable: boolean;
  is_feedback: boolean;
  semantic_role?: string | null;
  visibility: string;
};

export type UIStateDetailResponse = UIStateSummary & {
  ui_elements: UIElementRecord[];
  feedback_elements: any[];
  primary_action_candidates: any[];
};

export type SemanticCanonicalizationResult = {
  canonical_state_set_id: string;
  canonical_states: Array<{
    canonical_state_id: string;
    representative_state_id: string;
    member_state_ids: string[];
    canonical_summary: string;
    merge_rationale: string;
  }>;
};

export type FlowSummary = {
  flow_id: string;
  flow_label: string;
  flow_type: string;
  entry_state_id?: string | null;
  state_ids: string[];
  terminal_state_ids: string[];
};

export type FlowsListResponse = {
  run_id: string;
  total: number;
  flows: FlowSummary[];
};

export type FlowDetailResponse = FlowSummary & {
  transitions: Array<{
    transition_id: string;
    from_state_id: string;
    to_state_id: string;
    action_type: string;
    transition_basis: string;
  }>;
};

export type TransitionVisualValidationResult = {
  validated_flows: Array<{
    flow_id: string;
    transitions: Array<{
      transition_id: string;
      visual_delta: {
        added_elements: any[];
        removed_elements: any[];
      };
      transition_support: string;
    }>;
  }>;
};

export type BehaviourIntentSummary = {
  intent_id: string;
  intent_name: string;
  domain: string;
  intent_scope: string;
  user_goal: string;
  grounding_level: string;
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
};

export type ScenariosListResponse = {
  run_id: string;
  total: number;
  scenarios: ScenarioSummary[];
};

export type ScenarioDetailResponse = {
  scenario_id: string;
  scenario_title: string;
  gherkin_text: string;
  bdd_steps: Array<{
    step_id: string;
    keyword: string;
    text: string;
    inference_level: string;
  }>;
  validation?: {
    validation_status: string;
    final_reliability: number;
    hallucination_flags: Record<string, boolean>;
  };
};

export type ScenarioValidationResult = {
  validated_scenarios: Array<{
    scenario_id: string;
    validation_status: string;
    final_reliability: number;
    acceptance_decision: {
      include_in_final_output: boolean;
      reason: string;
    };
  }>;
  /** Agent 7 summary counts (snake_case from backend model_dump). */
  final_output_summary?: {
    validated_count?: number;
    rejected_count?: number;
    low_confidence_count?: number;
    needs_revision_count?: number;
    total_count?: number;
  };
};
