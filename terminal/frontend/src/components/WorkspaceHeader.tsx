import type { WorkspaceMode } from "./ModePanel";

interface WorkspaceHeaderProps {
  accountOpen: boolean;
  mode: WorkspaceMode;
  onAccountToggle: () => void;
  symbol: string;
}

export function WorkspaceHeader({
  accountOpen,
  mode,
  onAccountToggle,
  symbol,
}: WorkspaceHeaderProps) {
  return (
    <header className="workspace-header">
      <div className="instrument-block">
        <p className="eyebrow">Trading Workspace · {mode}</p>
        <h1>{symbol}</h1>
        <p className="instrument-note">5m · Development market feed</p>
      </div>
      <div className="header-actions">
        <div
          className="mode-badge"
          role="status"
          aria-label="Execution mode: paper, non-live"
        >
          <span>PAPER</span>
          <small>NON-LIVE</small>
        </div>
        <button
          aria-expanded={accountOpen}
          aria-label="Open account selection"
          className="icon-button"
          onClick={onAccountToggle}
          type="button"
        >
          🔑
        </button>
      </div>
    </header>
  );
}
