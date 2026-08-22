import { useState } from "react";
import { AccountMenu } from "../components/AccountMenu";
import { ChartPanel } from "../components/ChartPanel";
import { DomPanel } from "../components/DomPanel";
import { ModePanel, type WorkspaceMode } from "../components/ModePanel";
import { TapePanel } from "../components/TapePanel";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import { useMarketData } from "../marketData/useMarketData";

export function App() {
  const [mode, setMode] = useState<WorkspaceMode>("TERMINAL");
  const [zoom, setZoom] = useState(1);
  const [accountOpen, setAccountOpen] = useState(false);
  const market = useMarketData();

  return (
    <main className="workspace-shell">
      <WorkspaceHeader
        accountOpen={accountOpen}
        mode={mode}
        onAccountToggle={() => setAccountOpen((open) => !open)}
        symbol={market.book.symbol}
      />
      {accountOpen ? <AccountMenu /> : null}
      <section className="workspace-grid" aria-label="Trading workspace">
        <ChartPanel candles={market.candles} onZoom={setZoom} zoom={zoom} />
        <aside className="market-sidecar" aria-label="Market depth and tape">
          <DomPanel book={market.book} ownOrders={market.ownOrders} />
          <TapePanel trades={market.trades} />
        </aside>
        <ModePanel mode={mode} onModeChange={setMode} />
      </section>
      <footer className="status-bar">
        <span className="status-dot" aria-hidden="true" />
        <span>Market data: deterministic development feed</span>
        <span>Book: {market.book.health}</span>
        <span>Execution: PAPER / non-live</span>
      </footer>
    </main>
  );
}
