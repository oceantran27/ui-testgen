/**
 * Ordered LangGraph nodes (excluding START/END), matching `be/app/graph/runner/graph_runner.py`.
 */
export const PIPELINE_NODE_IDS = [
  "init_run_context_node",
  "joint_screen_understanding_node",
  "representation_compression_node",
  "global_flow_discovery_node",
  "generate_tests_node",
  "scenario_evidence_audit_node",
  "output_assembly_node",
  "graph_finalizer_node",
] as const;

export type PipelineNodeId = (typeof PIPELINE_NODE_IDS)[number];

export const PIPELINE_STEP_LABELS: Record<PipelineNodeId, string> = {
  init_run_context_node: "Init context",
  joint_screen_understanding_node: "Analyze screens",
  representation_compression_node: "Compress representation",
  global_flow_discovery_node: "Discover flows",
  generate_tests_node: "Generate tests",
  scenario_evidence_audit_node: "Audit scenarios",
  output_assembly_node: "Assembly",
  graph_finalizer_node: "Finalize",
};
