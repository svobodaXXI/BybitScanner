export function WorkspaceHeader() {
  return (
    <header className="workspace-header">
      <div>
        <p className="eyebrow">Trading Workspace</p>
        <h1>BTCUSDT</h1>
        <p className="instrument-note">Instrument placeholder</p>
      </div>
      <div
        className="mode-badge"
        role="status"
        aria-label="Execution mode: paper, non-live"
      >
        <span>PAPER</span>
        <small>NON-LIVE</small>
      </div>
    </header>
  );
}
