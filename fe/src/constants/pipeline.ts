/**
 * Ordered LangGraph nodes (excluding START/END), matching
 * `be/app/graph/runner/graph_runner.py`.
 */
export const PIPELINE_NODE_IDS = [
  "init_run_context_node",
  "ui_state_extraction_node",
  "llm_flow_discovery_node",
  "behaviour_intent_inference_node",
  "behaviour_scenario_generation_node",
  "scenario_validation_node",
  "output_assembly_node",
  "graph_finalizer_node",
] as const;

export type PipelineNodeId = (typeof PIPELINE_NODE_IDS)[number];

export const PIPELINE_STEP_LABELS: Record<PipelineNodeId, string> = {
  init_run_context_node: "Init context",
  ui_state_extraction_node: "A1: UI Extraction",
  llm_flow_discovery_node: "A3: Flow Discovery",
  behaviour_intent_inference_node: "A5: Intent Inference",
  behaviour_scenario_generation_node: "A6: Scenario Generation",
  scenario_validation_node: "A7: Validation",
  output_assembly_node: "Assembly",
  graph_finalizer_node: "Finalize",
};
