import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ReplayPage } from "./ReplayPage";

const root = document.getElementById("replay-root");
if (!root) throw new Error("Replay root is missing");
createRoot(root).render(<StrictMode><ReplayPage /></StrictMode>);
