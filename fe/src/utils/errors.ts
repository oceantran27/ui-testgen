import axios from "axios";

export function extractApiError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | { detail?: unknown; message?: string; error_code?: string }
      | undefined;
    if (typeof data?.message === "string" && data.message.trim()) {
      const code =
        typeof data.error_code === "string" ? ` [${data.error_code}]` : "";
      return `${data.message.trim()}${code}`;
    }
    const detail = data?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (detail && typeof detail === "object" && "message" in detail) {
      const m = (detail as { message?: string }).message;
      if (typeof m === "string" && m.trim()) {
        return m;
      }
    }
    if (Array.isArray(detail) && detail.length > 0) {
      return JSON.stringify(detail);
    }
    return error.message || "An unknown error occurred.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unknown error occurred.";
}
