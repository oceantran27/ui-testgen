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

const NODE_INDEX: Record<string, number> = Object.fromEntries(
  PIPELINE_NODE_IDS.map((id, i) => [id, i]),
);

/**
 * Backend `persist_run_graph_progress` uses *_node ids; graph state may use shorter names.
 */
const PIPELINE_NODE_ALIASES: Record<string, PipelineNodeId> = {
  ui_state_extraction: "ui_state_extraction_node",
  behaviour_intent_inference: "behaviour_intent_inference_node",
  behaviour_scenario_generation: "behaviour_scenario_generation_node",
  scenario_validation: "scenario_validation_node",
};

export function normalizePipelineNodeId(
  raw: string | null | undefined,
): PipelineNodeId | null {
  if (!raw) {
    return null;
  }
  if ((PIPELINE_NODE_IDS as readonly string[]).includes(raw)) {
    return raw as PipelineNodeId;
  }
  return PIPELINE_NODE_ALIASES[raw] ?? null;
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
function activeIndexFromProgressPercentage(pct: number): number {
  const n = PIPELINE_NODE_IDS.length;
  const clamped = Math.max(1, Math.min(99, Math.round(pct)));
  return Math.min(n - 1, Math.max(0, Math.ceil((clamped / 100) * n) - 1));
}

function heuristicActiveIndex(
  hints: PipelineHints | undefined,
): number | null {
  if (!hints) {
    return null;
  }
  if (hints.scenarioCount > 0) {
    return NODE_INDEX["scenario_validation_node"] ?? null;
  }
  if (hints.flowCount > 0) {
    return NODE_INDEX["behaviour_intent_inference_node"] ?? null;
  }
  if (hints.uiStateCount > 0) {
    return NODE_INDEX["llm_flow_discovery_node"] ?? null;
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
  if (normalized != null && NODE_INDEX[normalized] !== undefined) {
    activeIdx = NODE_INDEX[normalized];
  }

  if (activeIdx === null) {
    const pctRaw = eff.progress_percentage;
    const pctNum = pctRaw == null ? NaN : Number(pctRaw);
    const inFlight =
      run?.status === "processing" || graphStatusVal === "running";
    if (inFlight && !Number.isNaN(pctNum)) {
      activeIdx = activeIndexFromProgressPercentage(pctNum);
    }
  }

  if (activeIdx === null && processing && hints) {
    activeIdx = heuristicActiveIndex(hints);
  }

  /* Queued / starting: no node yet — show first step as active */
  if (
    activeIdx === null &&
    (run?.status === "queued" || run?.status === "uploaded") &&
    graphStatusVal !== "running"
  ) {
    activeIdx = 0;
  }

  return PIPELINE_NODE_IDS.map((id, idx) => {
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
