export type PipelinePhaseId =
  | "dedupe"
  | "parallel_screens"
  | "state_graph"
  | "e2e_scenarios";

export type PipelinePhaseUiStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export type RunStatus = "queued" | "running" | "completed" | "failed";

export interface PipelinePhaseProgress {
  id: PipelinePhaseId;
  label: string;
  status: PipelinePhaseUiStatus;
  started_at_iso: string | null;
  ended_at_iso: string | null;
  duration_ms: number | null;
}

export interface PipelinePhaseTiming {
  phase_id: PipelinePhaseId;
  label: string;
  duration_ms: number;
}

export interface PipelineRunTiming {
  phases: PipelinePhaseTiming[];
  wall_clock_ms: number;
}

export interface GherkinTestScenarioPair {
  scenario: string;
  gherkin: string;
}

export interface IsolatedScenariosOutput {
  image_id: string;
  scenarios: GherkinTestScenarioPair[];
}

export interface FlowScenariosOutput {
  flow_id: string;
  scenarios: GherkinTestScenarioPair[];
}

export interface FinalTestOutputPayload {
  isolated_scenarios: IsolatedScenariosOutput[];
  flow_scenarios: FlowScenariosOutput[];
}

export interface StateGraphFlowItemPayload {
  id: string;
  name: string;
  nodes: string[];
}

export interface StateGraphOrganizeResponsePayload {
  model: string;
  input_id: string;
  flows: StateGraphFlowItemPayload[];
  final_test_output: FinalTestOutputPayload;
  pipeline_timing?: PipelineRunTiming | null;
  /** Canonical image_id (sha256 hex) → uploaded filename under `/uploads/state-graph-input/{input_id}/`. */
  screen_images?: Record<string, string>;
}

export interface StateGraphStartResponsePayload {
  input_id: string;
  status: "running";
}

export interface StateGraphRunStatusResponsePayload {
  input_id: string;
  status: RunStatus;
  current_phase?: PipelinePhaseId | null;
  phases: PipelinePhaseProgress[];
  error?: string | null;
  result?: StateGraphOrganizeResponsePayload | null;
  timing?: PipelineRunTiming | null;
}
