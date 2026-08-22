import { WorkspaceHeader } from "../components/WorkspaceHeader";
import { WorkspacePanel } from "../components/WorkspacePanel";

export function App() {
  return (
    <main className="workspace-shell">
      <WorkspaceHeader />
      <section className="workspace-grid" aria-label="Trading workspace">
        <WorkspacePanel className="chart-panel" title="Chart">
          Interactive chart foundation reserved for a later block.
        </WorkspacePanel>
        <WorkspacePanel className="dom-panel" title="DOM / Order book">
          Normalized market depth will appear here.
        </WorkspacePanel>
        <WorkspacePanel className="controls-panel" title="Trading controls">
          Execution controls are intentionally unavailable in this foundation.
        </WorkspacePanel>
      </section>
      <footer className="status-bar">
        <span className="status-dot" aria-hidden="true" />
        <span>Market data: not connected</span>
        <span>Execution: PAPER foundation only</span>
      </footer>
    </main>
  );
}
