/**
 * Ordered LangGraph nodes (excluding START/END), matching `be/app/graph/runner/graph_runner.py`.
 *
 * Default export follows **separated** mode (`SCREEN_UNDERSTANDING_MODE=separated`) — two analyse steps.
 * For joint runs (`screen_understanding_mode: "joint"` in run config), use `PIPELINE_NODE_IDS_JOINT`.
 */
export const PIPELINE_NODE_IDS_SEPARATED = [
  "init_run_context_node",
  "ui_state_evidence_extraction_node",
  "screen_intent_extraction_v2_node",
  "representation_compression_node",
  "global_flow_discovery_node",
  "generate_tests_node",
  "scenario_evidence_audit_node",
  "output_assembly_node",
  "graph_finalizer_node",
] as const;

export const PIPELINE_NODE_IDS_JOINT = [
  "init_run_context_node",
  "joint_screen_understanding_node",
  "representation_compression_node",
  "global_flow_discovery_node",
  "generate_tests_node",
  "scenario_evidence_audit_node",
  "output_assembly_node",
  "graph_finalizer_node",
] as const;

/** Alias for the default backend mode (`separated`). */
export const PIPELINE_NODE_IDS = PIPELINE_NODE_IDS_SEPARATED;

export type PipelineNodeId =
  | (typeof PIPELINE_NODE_IDS_SEPARATED)[number]
  | (typeof PIPELINE_NODE_IDS_JOINT)[number];

export const PIPELINE_STEP_LABELS: Record<PipelineNodeId, string> = {
  init_run_context_node: "Init context",
  joint_screen_understanding_node: "Analyze screens (joint)",
  ui_state_evidence_extraction_node: "Analyze screens — UI evidence",
  screen_intent_extraction_v2_node: "Analyze screens — local intents",
  representation_compression_node: "Compress representation",
  global_flow_discovery_node: "Discover flows",
  generate_tests_node: "Generate tests",
  scenario_evidence_audit_node: "Audit scenarios",
  output_assembly_node: "Assembly",
  graph_finalizer_node: "Finalize",
};
