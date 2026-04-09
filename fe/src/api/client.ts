import axios from "axios";

const normalizedApiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1")
  .trim()
  .replace(/\/+$/, "");

export const apiClient = axios.create({
  baseURL: normalizedApiBaseUrl,
  timeout: 3000000,
});
