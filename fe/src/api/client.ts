import axios from "axios";

export const normalizedApiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1")
  .trim()
  .replace(/\/+$/, "");

export const apiClient = axios.create({
  baseURL: normalizedApiBaseUrl,
  timeout: 3000000,
});

/** Absolute URL for `<img src>` and window navigation (redirecting routes). */
export function apiAbsoluteUrl(relativePath: string): string {
  const path = relativePath.replace(/^\/+/, "");
  if (normalizedApiBaseUrl.startsWith("http")) {
    return `${normalizedApiBaseUrl}/${path}`;
  }
  const origin =
    typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}${normalizedApiBaseUrl.startsWith("/") ? "" : "/"}${normalizedApiBaseUrl}/${path}`;
}
