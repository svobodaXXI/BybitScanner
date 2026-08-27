import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const paperBackendUrl = (
  globalThis as { process?: { env?: Record<string, string | undefined> } }
).process?.env?.PAPER_BACKEND_URL;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    allowedHosts: [
      ".trycloudflare.com",
      ".pinggy-free.link",
      ".free.pinggy.net",
      ".lhr.life",
    ],
    proxy: {
      "/api": {
        target: paperBackendUrl ?? "http://127.0.0.1:8765",
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (proxyReq, req) => {
            console.log("VITE API IN", req.method, req.url);
            console.log("VITE API PROXY_REQ", proxyReq.method, proxyReq.path);
            req.on("aborted", () => {
              console.log("VITE API IN ABORTED", req.method, req.url);
            });
            req.on("close", () => {
              console.log("VITE API IN CLOSE", req.method, req.url);
            });
          });
          proxy.on("proxyRes", (proxyRes, req) => {
            console.log(
              "VITE API PROXY_RES",
              proxyRes.statusCode,
              req.method,
              req.url,
            );
            proxyRes.on("aborted", () => {
              console.log("VITE API PROXY_RES ABORTED", req.method, req.url);
            });
            proxyRes.on("close", () => {
              console.log("VITE API PROXY_RES CLOSE", req.method, req.url);
            });
          });
          proxy.on("error", (error, req) => {
            console.error(
              "VITE API PROXY_ERROR",
              req.method,
              req.url,
              error.name,
              error.message,
            );
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
  },
});
