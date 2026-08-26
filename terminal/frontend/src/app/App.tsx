import { useEffect, useState } from "react";
import { AccountMenu } from "../components/AccountMenu";
import { ChartPanel } from "../components/ChartPanel";
import { DomPanel } from "../components/DomPanel";
import { ModePanel, type WorkspaceMode } from "../components/ModePanel";
import { TapePanel } from "../components/TapePanel";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import { recommendedLadderCenter } from "../marketData/domProjection";
import { useMarketData } from "../marketData/useMarketData";
import { TelegramMiniAppBridge } from "../telegram/TelegramMiniAppBridge";

export function App() {
  const [mode, setMode] = useState<WorkspaceMode>("TERMINAL");
  const [accountOpen, setAccountOpen] = useState(false);
  const [ladderCenterPrice, setLadderCenterPrice] = useState<number | null>(
    null,
  );
  const market = useMarketData();

  useEffect(() => {
    if (market.book.health !== "READY") return;
    setLadderCenterPrice(
      (current) => current ?? recommendedLadderCenter(market.book),
    );
  }, [market.book]);

  return (
    <main className="workspace-shell">
      <TelegramMiniAppBridge />
      <WorkspaceHeader
        accountOpen={accountOpen}
        mode={mode}
        onAccountToggle={() => setAccountOpen((open) => !open)}
        symbol={market.book.symbol}
      />
      {accountOpen ? <AccountMenu /> : null}
      <section className="workspace-grid" aria-label="Trading workspace">
        <ChartPanel
          candles={market.candles}
          symbol={market.book.symbol}
          timeframe="5m"
        />
        <aside className="market-sidecar" aria-label="Market depth and tape">
          <DomPanel
            book={market.book}
            centerPrice={ladderCenterPrice}
            onCenterPriceChange={setLadderCenterPrice}
            ownOrders={market.ownOrders}
          />
          <TapePanel
            book={market.book}
            centerPrice={ladderCenterPrice}
            trades={market.trades}
          />
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
