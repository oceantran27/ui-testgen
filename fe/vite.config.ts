import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  /** Where Vite forwards `/api` and `/uploads` in dev (`npm run dev`). Override in `.env`: VITE_DEV_API_PROXY_TARGET */
  const apiTarget =
    env.VITE_DEV_API_PROXY_TARGET?.trim() || "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
        "/uploads": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
