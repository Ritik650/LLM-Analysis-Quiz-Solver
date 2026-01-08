import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the FastAPI backend so the browser talks to
// one origin (avoids CORS in development). In production VITE_API_BASE points
// directly at the deployed HF Space.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:7860",
      "/solve": "http://localhost:7860",
      "/runs": "http://localhost:7860",
      "/healthz": "http://localhost:7860",
    },
  },
});
