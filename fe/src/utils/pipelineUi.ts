import type { GraphStatusResponse } from "../types/run";
import type { RunResponse } from "../types/run";
import {
  PIPELINE_NODE_IDS,
  PIPELINE_STEP_LABELS,
  type PipelineNodeId,
} from "../constants/pipeline";

export type PipelineStepUiStatus = "pending" | "running" | "done" | "failed";

export type PipelineStepRow = {
  id: PipelineNodeId;
  label: string;
  status: PipelineStepUiStatus;
};

export type PipelineHints = {
  uiStateCount: number;
  flowCount: number;
  scenarioCount: number;
};

/** Map legacy backend node / agent names to the single screen-understanding step. */
const PIPELINE_NODE_ALIASES: Record<string, PipelineNodeId> = {
  ui_state_evidence_extraction: "joint_screen_understanding_node",
  ui_state_evidence_extraction_node: "joint_screen_understanding_node",
  screen_intent_extraction_v2: "joint_screen_understanding_node",
  screen_intent_extraction_v2_node: "joint_screen_understanding_node",
  joint_screen_understanding: "joint_screen_understanding_node",
  compressed_representation: "representation_compression_node",
  representation_compression: "representation_compression_node",
  global_flow_discovery: "global_flow_discovery_node",
  flow_context_builder: "global_flow_discovery_node",
  transition_evidence: "global_flow_discovery_node",
  intent_aware_flow_discovery: "global_flow_discovery_node",
  discover_flows: "global_flow_discovery_node",
  behaviour_contract_builder: "generate_tests_node",
  behaviour_scenario_generation: "generate_tests_node",
  generate_tests: "generate_tests_node",
  scenario_evidence_audit: "scenario_evidence_audit_node",
};

export function normalizePipelineNodeId(
  raw: string | null | undefined,
): PipelineNodeId | null {
  if (!raw) {
    return null;
  }
  const aliased = PIPELINE_NODE_ALIASES[raw];
  if (aliased) {
    return aliased;
  }
  if (raw in PIPELINE_STEP_LABELS) {
    return raw as PipelineNodeId;
  }
  return null;
}

/** Merge `GET /runs/:id` (primary) with optional `/graph-status` for pipeline fields. */
function effectivePipelineFields(
  run: RunResponse | null,
  graph: GraphStatusResponse | null,
): {
  current_node: string | null | undefined;
  progress_percentage: number | null | undefined;
  graph_status: string | null | undefined;
} {
  return {
    current_node: run?.current_node ?? graph?.current_node,
    progress_percentage:
      run?.progress_percentage ?? graph?.progress_percentage,
    graph_status: run?.graph_status ?? graph?.graph_status,
  };
}

/** Inverse of BE `progress_percentage = clamp(1..99, int((idx + 1) / n * 100))`. */
function activeIndexFromProgressPercentage(pct: number, totalSteps: number): number {
  const clamped = Math.max(1, Math.min(99, Math.round(pct)));
  return Math.min(totalSteps - 1, Math.max(0, Math.ceil((clamped / 100) * totalSteps) - 1));
}

function heuristicActiveIndex(
  hints: PipelineHints | undefined,
  nodeIndex: Record<string, number>,
): number | null {
  if (!hints) {
    return null;
  }
  if (hints.scenarioCount > 0) {
    return nodeIndex["scenario_evidence_audit_node"] ?? null;
  }
  if (hints.flowCount > 0) {
    return nodeIndex["generate_tests_node"] ?? null;
  }
  if (hints.uiStateCount > 0) {
    return nodeIndex["global_flow_discovery_node"] ?? null;
  }
  return null;
}

/**
 * Derive per-step UI status from run lifecycle + DB-backed node / progress.
 */
export function buildPipelineStepRows(
  run: RunResponse | null,
  graph: GraphStatusResponse | null,
  hints?: PipelineHints,
): PipelineStepRow[] {
  const eff = effectivePipelineFields(run, graph);

  const nodeIds = PIPELINE_NODE_IDS;
  const nodeIndex: Record<string, number> = Object.fromEntries(
    nodeIds.map((id, i) => [id, i]),
  );

  const failed = run?.status === "failed";
  const completed = run?.status === "completed";
  const graphStatusVal = eff.graph_status;
  const processing =
    run?.status === "processing" ||
    run?.status === "queued" ||
    run?.status === "uploaded" ||
    graphStatusVal === "running";

  let activeIdx: number | null = null;

  const normalized = normalizePipelineNodeId(eff.current_node);
  if (normalized != null && nodeIndex[normalized] !== undefined) {
    activeIdx = nodeIndex[normalized];
  }

  if (activeIdx === null) {
    const pctRaw = eff.progress_percentage;
    const pctNum = pctRaw == null ? NaN : Number(pctRaw);
    const inFlight =
      run?.status === "processing" || graphStatusVal === "running";
    if (inFlight && !Number.isNaN(pctNum)) {
      activeIdx = activeIndexFromProgressPercentage(pctNum, nodeIds.length);
    }
  }

  if (activeIdx === null && processing && hints) {
    activeIdx = heuristicActiveIndex(hints, nodeIndex);
  }

  /* Queued / starting: no node yet — show first step as active */
  if (
    activeIdx === null &&
    (run?.status === "queued" || run?.status === "uploaded") &&
    graphStatusVal !== "running"
  ) {
    activeIdx = 0;
  }

  return nodeIds.map((id, idx) => {
    const label = PIPELINE_STEP_LABELS[id];
    if (failed) {
      if (activeIdx !== null) {
        if (idx < activeIdx) {
          return { id, label, status: "done" as const };
        }
        if (idx === activeIdx) {
          return { id, label, status: "failed" as const };
        }
        return { id, label, status: "pending" as const };
      }
      return {
        id,
        label,
        status: "pending" as const,
      };
    }
    if (completed) {
      return { id, label, status: "done" as const };
    }
    if (activeIdx !== null) {
      if (idx < activeIdx) {
        return { id, label, status: "done" as const };
      }
      if (idx === activeIdx) {
        return { id, label, status: "running" as const };
      }
    }
    return { id, label, status: "pending" as const };
  });
}
