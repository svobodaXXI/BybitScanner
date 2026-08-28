import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

type DiagnosticRequest = {
  method?: string;
  path?: string;
  url?: string;
  statusCode?: number;
  on(event: "aborted" | "close", listener: () => void): void;
};
type DiagnosticProxy = {
  on(event: "proxyReq", listener: (proxyReq: DiagnosticRequest, req: DiagnosticRequest) => void): void;
  on(event: "proxyRes", listener: (proxyRes: DiagnosticRequest, req: DiagnosticRequest) => void): void;
  on(event: "error", listener: (error: Error, req: DiagnosticRequest) => void): void;
};

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
          const diagnosticProxy = proxy as unknown as DiagnosticProxy;
          diagnosticProxy.on("proxyReq", (proxyReq, req) => {
            console.log("VITE API IN", req.method, req.url);
            console.log("VITE API PROXY_REQ", proxyReq.method, proxyReq.path);
            req.on("aborted", () => {
              console.log("VITE API IN ABORTED", req.method, req.url);
            });
            req.on("close", () => {
              console.log("VITE API IN CLOSE", req.method, req.url);
            });
          });
          diagnosticProxy.on("proxyRes", (proxyRes, req) => {
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
          diagnosticProxy.on("error", (error, req) => {
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
  preview: {
    host: "0.0.0.0",
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
