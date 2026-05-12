import { apiClient } from "./client";
import type {
  ArtifactsResponse,
  BehaviourIntentsListResponse,
  FlowDetailResponse,
  FlowsListResponse,
  GraphStatusResponse,
  ImageListResponse,
  ModelCallDetailResponse,
  ModelCallsListResponse,
  ModelConfigResponse,
  RunCancelResponse,
  RunCreateBody,
  RunListResponse,
  RunResponse,
  RunSubmitResponse,
  ScenariosListResponse,
  ScenarioDetailResponse,
  UIStateDetailResponse,
  UIStatesListResponse,
  UploadImagesResponse,
  PipelineLogResponse,
  SemanticCanonicalizationResult,
  ScenarioValidationResult,
} from "../types/run";

export async function createRun(body: RunCreateBody = {}): Promise<RunResponse> {
  const { data } = await apiClient.post<RunResponse>("runs", body);
  return data;
}

export async function listRuns(): Promise<RunListResponse> {
  const { data } = await apiClient.get<RunListResponse>("runs");
  return data;
}

export async function getRun(runId: string): Promise<RunResponse> {
  const { data } = await apiClient.get<RunResponse>(
    `runs/${encodeURIComponent(runId)}`,
  );
  return data;
}

export async function uploadRunImages(
  runId: string,
  files: File[],
): Promise<UploadImagesResponse> {
  const formData = new FormData();
  for (const f of files) {
    formData.append("files", f);
  }
  const { data } = await apiClient.post<UploadImagesResponse>(
    `runs/${encodeURIComponent(runId)}/images`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

export async function listRunImages(
  runId: string,
  params?: { quality_status?: string; is_canonical?: boolean },
): Promise<ImageListResponse> {
  const { data } = await apiClient.get<ImageListResponse>(
    `runs/${encodeURIComponent(runId)}/images`,
    { params },
  );
  return data;
}

export async function submitRun(runId: string): Promise<RunSubmitResponse> {
  const { data } = await apiClient.post<RunSubmitResponse>(
    `runs/${encodeURIComponent(runId)}/submit`,
  );
  return data;
}

export async function cancelRun(runId: string): Promise<RunCancelResponse> {
  const { data } = await apiClient.post<RunCancelResponse>(
    `runs/${encodeURIComponent(runId)}/cancel`,
  );
  return data;
}

export async function deleteRun(runId: string): Promise<void> {
  await apiClient.delete(`runs/${encodeURIComponent(runId)}`);
}

export async function getGraphStatus(runId: string): Promise<GraphStatusResponse> {
  const { data } = await apiClient.get<GraphStatusResponse>(
    `runs/${encodeURIComponent(runId)}/graph-status`,
  );
  return data;
}

export async function getRunPipelineLog(
  runId: string,
  params?: { from_byte?: number },
): Promise<PipelineLogResponse> {
  const { data } = await apiClient.get<PipelineLogResponse>(
    `runs/${encodeURIComponent(runId)}/pipeline-log`,
    { params: params?.from_byte != null ? { from_byte: params.from_byte } : undefined },
  );
  return data;
}

export async function getArtifacts(runId: string): Promise<ArtifactsResponse> {
  const { data } = await apiClient.get<ArtifactsResponse>(
    `runs/${encodeURIComponent(runId)}/artifacts`,
  );
  return data;
}

export async function listModelCalls(runId: string): Promise<ModelCallsListResponse> {
  const { data } = await apiClient.get<ModelCallsListResponse>(
    `runs/${encodeURIComponent(runId)}/model-calls`,
  );
  return data;
}

export async function getModelCall(
  runId: string,
  callId: string,
): Promise<ModelCallDetailResponse> {
  const { data } = await apiClient.get<ModelCallDetailResponse>(
    `runs/${encodeURIComponent(runId)}/model-calls/${encodeURIComponent(callId)}`,
  );
  return data;
}

export async function getModelConfig(runId: string): Promise<ModelConfigResponse> {
  const { data } = await apiClient.get<ModelConfigResponse>(
    `runs/${encodeURIComponent(runId)}/model-config`,
  );
  return data;
}

export async function listUIStates(runId: string): Promise<UIStatesListResponse> {
  const { data } = await apiClient.get<UIStatesListResponse>(
    `runs/${encodeURIComponent(runId)}/states`,
  );
  return data;
}

export async function getUIState(
  runId: string,
  stateId: string,
): Promise<UIStateDetailResponse> {
  const { data } = await apiClient.get<UIStateDetailResponse>(
    `runs/${encodeURIComponent(runId)}/states/${encodeURIComponent(stateId)}`,
  );
  return data;
}

export async function getCanonicalStates(runId: string): Promise<SemanticCanonicalizationResult> {
  const { data } = await apiClient.get<SemanticCanonicalizationResult>(
    `runs/${encodeURIComponent(runId)}/canonical-states`,
  );
  return data;
}

export async function listFlows(runId: string): Promise<FlowsListResponse> {
  const { data } = await apiClient.get<FlowsListResponse>(
    `runs/${encodeURIComponent(runId)}/flows`,
  );
  return data;
}

export async function getFlowDetail(
  runId: string,
  flowId: string,
): Promise<FlowDetailResponse> {
  const { data } = await apiClient.get<FlowDetailResponse>(
    `runs/${encodeURIComponent(runId)}/flows/${encodeURIComponent(flowId)}`,
  );
  return data;
}

export async function listBehaviourIntents(
  runId: string,
): Promise<BehaviourIntentsListResponse> {
  const { data } = await apiClient.get<BehaviourIntentsListResponse>(
    `runs/${encodeURIComponent(runId)}/behaviour-intents`,
  );
  return data;
}

export async function listScenarios(runId: string): Promise<ScenariosListResponse> {
  const { data } = await apiClient.get<ScenariosListResponse>(
    `runs/${encodeURIComponent(runId)}/scenarios`,
  );
  return data;
}

export async function getScenarioDetail(
  runId: string,
  scenarioId: string,
): Promise<ScenarioDetailResponse> {
  const { data } = await apiClient.get<ScenarioDetailResponse>(
    `runs/${encodeURIComponent(runId)}/scenarios/${encodeURIComponent(scenarioId)}`,
  );
  return data;
}

export async function getScenarioValidation(runId: string): Promise<ScenarioValidationResult> {
  const { data } = await apiClient.get<ScenarioValidationResult>(
    `runs/${encodeURIComponent(runId)}/scenario-validation`,
  );
  return data;
}

export async function getResearchOutput(
  runId: string,
): Promise<ScenarioValidationResult> {
  const { data } = await apiClient.get<ScenarioValidationResult>(
    `runs/${encodeURIComponent(runId)}/research-output`,
  );
  return data;
}
