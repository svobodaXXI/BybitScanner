import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Local Windows utility only. Never part of the terminal/Autopilot bundle.
// Build with npm run build:replay; serve with research/local_replay_viewer/server.py.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../../research/local_replay_viewer/dist",
    emptyOutDir: true,
    rollupOptions: {
      input: "replay.html",
    },
  },
});
