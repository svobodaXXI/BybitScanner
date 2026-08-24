import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const paperBackendUrl = (
  globalThis as { process?: { env?: Record<string, string | undefined> } }
).process?.env?.PAPER_BACKEND_URL;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    allowedHosts: [
      ".trycloudflare.com",
      ".pinggy-free.link",
      ".free.pinggy.net",
    ],
    proxy: {
      "/api": {
        target: paperBackendUrl ?? "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
