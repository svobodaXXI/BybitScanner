import { useEffect, useState } from "react";
import { AccountMenu } from "../components/AccountMenu";
import { ChartPanel } from "../components/ChartPanel";
import { DomPanel } from "../components/DomPanel";
import { ModePanel, type WorkspaceMode } from "../components/ModePanel";
import { TapePanel } from "../components/TapePanel";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import { recommendedLadderCenter } from "../marketData/domProjection";
import { type ChartTimeframe } from "../marketData/timeframes";
import { setMarketTimeframe, useMarketData } from "../marketData/useMarketData";
import { TelegramMiniAppBridge } from "../telegram/TelegramMiniAppBridge";

export function App() {
  const [mode, setMode] = useState<WorkspaceMode>("TERMINAL");
  const [accountOpen, setAccountOpen] = useState(false);
  const [domCompression, setDomCompression] = useState(3);
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("5m");
  const [positionSide, setPositionSide] = useState<"Long" | "Short" | "Flat">("Flat");
  const [positionAverageEntry, setPositionAverageEntry] = useState<number | null>(null);
  const [ladderCenterPrice, setLadderCenterPrice] = useState<number | null>(
    null,
  );
  const market = useMarketData();
  const bestBid = market.book.bids[0]?.price;
  const bestAsk = market.book.asks[0]?.price;
  const sizingReferencePrice =
    bestBid !== undefined && bestAsk !== undefined
      ? String((bestBid + bestAsk) / 2)
      : "0";
  const liveMidPrice =
    bestBid !== undefined && bestAsk !== undefined
      ? (bestBid + bestAsk) / 2
      : null;

  useEffect(() => {
    if (market.book.health !== "READY") return;
    setLadderCenterPrice(
      (current) => current ?? recommendedLadderCenter(market.book),
    );
  }, [market.book]);

  const changeTimeframe = (next: ChartTimeframe) => {
    setTimeframe(next);
    setMarketTimeframe(next);
  };

  return (
    <main className="workspace-shell">
      <TelegramMiniAppBridge />
      <WorkspaceHeader
        accountOpen={accountOpen}
        onAccountToggle={() => setAccountOpen((open) => !open)}
        onSymbolClick={() => {}}
        symbol={market.book.symbol}
        timeframe={timeframe}
        onTimeframeChange={changeTimeframe}
      />
      {accountOpen ? <AccountMenu /> : null}
      <section className="workspace-grid" aria-label="Trading workspace">
        <ChartPanel
          key={`${market.book.symbol}:${timeframe}`}
          candles={market.candles}
          tickSize={market.tickSize}
          symbol={market.book.symbol}
          timeframe={timeframe}
        />
        <aside className="market-sidecar" aria-label="Market depth and tape">
          <DomPanel
            book={market.book}
            centerPrice={ladderCenterPrice}
            onCenterPriceChange={setLadderCenterPrice}
            ownOrders={market.ownOrders}
            compression={domCompression}
            onCompressionChange={setDomCompression}
          />
          <TapePanel
            book={market.book}
            centerPrice={ladderCenterPrice}
            trades={market.trades}
            positionSide={positionSide}
            averageEntryPrice={positionAverageEntry}
            currentPrice={liveMidPrice}
            compression={domCompression}
          />
        </aside>
        <ModePanel
          mode={mode}
          onModeChange={setMode}
          sizingReferencePrice={sizingReferencePrice}
          onPositionSideChange={setPositionSide}
          onPositionAverageEntryChange={setPositionAverageEntry}
        />
      </section>
    </main>
  );
}


