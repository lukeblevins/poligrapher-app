import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: proxy API calls to the FastAPI process so the SPA and API share an origin.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
