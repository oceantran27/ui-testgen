import { apiClient } from "./client";
import type {
  StateGraphRunStatusResponsePayload,
  StateGraphStartResponsePayload,
} from "../types/stateGraph";

export type StateGraphRequestHeaders = {
  "X-Request-Id"?: string;
  "X-Batch-Id"?: string;
};

export async function postStateGraphPipelineStart(
  files: File[],
  headers?: StateGraphRequestHeaders,
): Promise<StateGraphStartResponsePayload> {
  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }
  const response = await apiClient.post<StateGraphStartResponsePayload>(
    "behavior-flows/state-graph",
    formData,
    { headers: { ...headers } },
  );
  return response.data;
}

export async function getStateGraphPipelineStatus(
  inputId: string,
): Promise<StateGraphRunStatusResponsePayload> {
  const response = await apiClient.get<StateGraphRunStatusResponsePayload>(
    `behavior-flows/state-graph/status/${encodeURIComponent(inputId)}`,
  );
  return response.data;
}

const sleep = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

export type PollPipelineOptions = {
  intervalMs?: number;
  maxWaitMs?: number;
  signal?: AbortSignal;
  onUpdate?: (payload: StateGraphRunStatusResponsePayload) => void;
};

/**
 * Polls until status is completed or failed, or maxWaitMs elapsed.
 */
export async function pollStateGraphUntilTerminal(
  inputId: string,
  options: PollPipelineOptions = {},
): Promise<StateGraphRunStatusResponsePayload> {
  const intervalMs = options.intervalMs ?? 1000;
  const maxWaitMs = options.maxWaitMs ?? 3_600_000;
  const started = Date.now();

  while (Date.now() - started < maxWaitMs) {
    if (options.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const snap = await getStateGraphPipelineStatus(inputId);
    options.onUpdate?.(snap);
    if (snap.status === "completed" || snap.status === "failed") {
      return snap;
    }
    await sleep(intervalMs);
    if (options.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
  }

  throw new Error("Pipeline polling timed out");
}
