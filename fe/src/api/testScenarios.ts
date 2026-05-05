import { apiClient } from "./client";
import type { TestScenarioSuite } from "../components/types";

export type TestScenarioRequestHeaders = {
  "X-Request-Id"?: string;
  "X-Batch-Id"?: string;
};

export async function postTestScenarioSuiteFromImage(
  file: File,
  headers?: TestScenarioRequestHeaders,
): Promise<TestScenarioSuite> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await apiClient.post<TestScenarioSuite>(
    "test-scenarios/from-image",
    formData,
    {
      headers: {
        ...headers,
      },
    },
  );
  return response.data;
}

export async function imageUrlToFile(
  url: string,
  filename = "screenshot.jpg",
): Promise<File> {
  const response = await fetch(url, { mode: "cors" });
  if (!response.ok) {
    throw new Error(`Failed to fetch image (${response.status})`);
  }
  const blob = await response.blob();
  const type = blob.type || "image/jpeg";
  return new File([blob], filename, { type });
}
