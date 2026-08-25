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
        <button
          aria-expanded={accountOpen}
          aria-label="Open account selection"
          className="account-switch-button"
          onClick={onAccountToggle}
          type="button"
        >
          <span className="account-switch-key" aria-hidden="true">
            <span className="account-key-head" />
            <span className="account-key-shaft" />
          </span>
          <span className="account-switch-label">
            <strong>PAPER</strong>
            <small>NON-LIVE</small>
          </span>
        </button>
      </div>
    </header>
  );
}
