import { apiClient } from "./client";
import type { BehaviorFlowOrganizeResponse } from "../types/behaviorFlow";

export type BehaviorFlowRequestHeaders = {
  "X-Request-Id"?: string;
  "X-Batch-Id"?: string;
};

export async function postBehaviorFlowOrganize(
  files: File[],
  headers?: BehaviorFlowRequestHeaders,
): Promise<BehaviorFlowOrganizeResponse> {
  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }
  const response = await apiClient.post<BehaviorFlowOrganizeResponse>(
    "behavior-flows/organize",
    formData,
    { headers: { ...headers } },
  );
  return response.data;
}
