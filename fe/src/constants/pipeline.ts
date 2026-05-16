/**
 * Ordered LangGraph nodes (excluding START/END), matching
 * `be/app/graph/runner/graph_runner.py`.
 */
export const PIPELINE_NODE_IDS = [
  "init_run_context_node",
  "ui_state_evidence_extraction_node",
  "screen_intent_extraction_v2_node",
  "flow_context_builder_node",
  "intent_aware_flow_discovery_node",
  "behaviour_contract_builder_node",
  "behaviour_scenario_generation_node",
  "scenario_evidence_audit_node",
  "output_assembly_node",
  "graph_finalizer_node",
] as const;

export type PipelineNodeId = (typeof PIPELINE_NODE_IDS)[number];

export const PIPELINE_STEP_LABELS: Record<PipelineNodeId, string> = {
  init_run_context_node: "Init context",
  ui_state_evidence_extraction_node: "A1: UI Extraction",
  screen_intent_extraction_v2_node: "A2: Screen Intent",
  flow_context_builder_node: "A3: Flow Context",
  intent_aware_flow_discovery_node: "A4: Flow Discovery",
  behaviour_contract_builder_node: "A5: Behaviour Contract",
  behaviour_scenario_generation_node: "A6: Scenario Generation",
  scenario_evidence_audit_node: "A7: Evidence Audit",
  output_assembly_node: "Assembly",
  graph_finalizer_node: "Finalize",
};
