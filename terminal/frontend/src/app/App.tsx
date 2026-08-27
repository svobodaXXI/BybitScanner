import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { AccountMenu } from "../components/AccountMenu";
import { ChartPanel } from "../components/ChartPanel";
import { DomPanel } from "../components/DomPanel";
import { ModePanel, type WorkspaceMode } from "../components/ModePanel";
import { TapePanel } from "../components/TapePanel";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import type {
  LimitCommandRequest,
  PaperLimitMutationResult,
  PaperState,
} from "../contracts/trading";
import { marketApiRoutes } from "../marketData/apiRoutes";
import { recommendedLadderCenter } from "../marketData/domProjection";
import type { ChartTimeframe } from "../marketData/timeframes";
import { setMarketTimeframe, useMarketData } from "../marketData/useMarketData";
import { TelegramMiniAppBridge } from "../telegram/TelegramMiniAppBridge";
import {
  createLimitDraft,
  EMPTY_LIMIT_DRAFT_STATE,
  limitDraftReducer,
  normalizeLimitDraftPrice,
} from "../orders/limitDraft";
import { PaperLimitDraftSubmitController } from "../orders/limitDraftSubmission";

const PAPER_STATE_REQUEST_TIMEOUT_MS = 5_000;

export function App() {
  const [mode, setMode] = useState<WorkspaceMode>("TERMINAL");
  const [accountOpen, setAccountOpen] = useState(false);
  const [domCompression, setDomCompression] = useState(3);
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("5m");
  const [positionSide, setPositionSide] = useState<"Long" | "Short" | "Flat">("Flat");
  const [positionAverageEntry, setPositionAverageEntry] = useState<number | null>(null);
  const [paperState, setPaperState] = useState<PaperState | null>(null);
  const [paperRefreshDebug, setPaperRefreshDebug] = useState("NOT_CALLED");
  const [fastLimitIntent, setFastLimitIntent] = useState<{
    side: "Buy" | "Sell";
    volumeUsdt: string;
  } | null>(null);
  const [limitDraftState, dispatchLimitDraft] = useReducer(
    limitDraftReducer,
    EMPTY_LIMIT_DRAFT_STATE,
  );
  const limitSubmitController = useRef(new PaperLimitDraftSubmitController());
  const paperRefreshInFlight = useRef(false);
  const [ladderCenterPrice, setLadderCenterPrice] = useState<number | null>(
    null,
  );
  const market = useMarketData();
  const tradingSymbol = market.book.symbol;
  const currentPaperState =
    paperState?.symbol === tradingSymbol ? paperState : null;
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

  const refreshPaperState = useCallback(async () => {
    if (paperRefreshInFlight.current) return;
    paperRefreshInFlight.current = true;
    setPaperRefreshDebug("CALLED");
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      PAPER_STATE_REQUEST_TIMEOUT_MS,
    );
    try {
      const response = await fetch(marketApiRoutes.paperState(tradingSymbol), {
        signal: controller.signal,
      });
      setPaperRefreshDebug(`RESPONSE:${response.status}`);
      if (!response.ok) {
        return;
      }
      const nextPaperState = (await response.json()) as PaperState;
      setPaperRefreshDebug(
        `JSON:${nextPaperState.symbol}:${nextPaperState.one_wv_usdt}`,
      );
      setPaperState(nextPaperState);
      setPaperRefreshDebug("SET_STATE");
    } catch (error) {
      setPaperRefreshDebug(
        `ERROR:${error instanceof Error ? error.message : String(error)}`,
      );
      return;
    } finally {
      window.clearTimeout(timeout);
      paperRefreshInFlight.current = false;
    }
  }, [tradingSymbol]);

  useEffect(() => {
    if (mode === "TERMINAL") void refreshPaperState();
  }, [mode, refreshPaperState]);

  useEffect(() => {
    if (mode !== "TERMINAL") return;

    const timer = window.setInterval(() => {
      void refreshPaperState();
    }, 500);

    return () => window.clearInterval(timer);
  }, [mode, refreshPaperState]);

  const changeTimeframe = (next: ChartTimeframe) => {
    setTimeframe(next);
    setMarketTimeframe(next);
  };

  const createFastLimitDraft = useCallback(
    (price: string) => {
      if (
        !fastLimitIntent ||
        market.book.health !== "READY" ||
        market.tickSize === null
      ) {
        return;
      }

      dispatchLimitDraft({
        type: "begin",
        draft: createLimitDraft({
          draftId: `limit-draft-${tradingSymbol}-${fastLimitIntent.side.toLowerCase()}-${Date.now()}`,
          symbol: tradingSymbol,
          side: fastLimitIntent.side,
          origin: "chart-fast",
          volume: { unit: "usdt", amount: fastLimitIntent.volumeUsdt },
          sizingReferencePrice,
          price,
          authoritativeTickSize: String(market.tickSize),
        }),
      });
    },
    [
      fastLimitIntent,
      market.book.health,
      market.tickSize,
      sizingReferencePrice,
      tradingSymbol,
    ],
  );

  const submitLimitDraft = useCallback((draftId?: string) => {
    const drafts =
      limitDraftState.drafts ??
      (limitDraftState.draft ? [limitDraftState.draft] : []);
    const draft = draftId
      ? drafts.find((candidate) => candidate.draftId === draftId) ?? null
      : limitDraftState.draft;
    if (!draft) return;
    const attempt = limitSubmitController.current.submit(draft, {
      dispatch: dispatchLimitDraft,
      createClientActionId: () =>
        globalThis.crypto?.randomUUID?.() ?? `paper-limit-${Date.now()}`,
      refreshPaperState,
    });
    return attempt.promise.then(() => undefined);
  }, [limitDraftState.draft, limitDraftState.drafts, refreshPaperState]);

  const submitDomLimit = useCallback(async (price: string) => {
    if (!fastLimitIntent || market.tickSize === null) return;
    const normalizedPrice = normalizeLimitDraftPrice(
      price,
      String(market.tickSize),
      fastLimitIntent.side,
    );
    if (normalizedPrice === null) return;
    const numericPrice = Number(normalizedPrice);
    if (
      (fastLimitIntent.side === "Buy" &&
        (bestAsk === undefined || numericPrice >= bestAsk)) ||
      (fastLimitIntent.side === "Sell" &&
        (bestBid === undefined || numericPrice <= bestBid))
    ) {
      return;
    }
    const request: LimitCommandRequest = {
      client_action_id:
        globalThis.crypto?.randomUUID?.() ?? `paper-dom-limit-${Date.now()}`,
      symbol: tradingSymbol,
      side: fastLimitIntent.side,
      volume: { unit: "usdt", amount: fastLimitIntent.volumeUsdt },
      sizing_reference_price: sizingReferencePrice,
      limit_price: normalizedPrice,
      time_in_force: "GTC",
    };
    try {
      const response = await fetch("/api/limit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const result = (await response.json()) as PaperLimitMutationResult;
      if (result.status === "completed") await refreshPaperState();
    } catch {
      return;
    }
  }, [
    bestAsk,
    bestBid,
    fastLimitIntent,
    market.tickSize,
    refreshPaperState,
    sizingReferencePrice,
    tradingSymbol,
  ]);

  return (
    <main className="workspace-shell">
      <TelegramMiniAppBridge />
      <div
        aria-label="PAPER STATE DEBUG"
        style={{
          position: "fixed",
          zIndex: 1000,
          top: 0,
          left: 0,
          right: 0,
          padding: "0.2rem 0.35rem",
          borderBottom: "1px solid #5bbcff",
          background: "#11181f",
          color: "#8fd3ff",
          fontSize: "0.65rem",
          lineHeight: 1.25,
          overflowWrap: "anywhere",
        }}
      >
        PAPER STATE DEBUG: refresh={paperRefreshDebug} | paperState.symbol=
        {paperState?.symbol ?? "null"} | paperState.one_wv_usdt=
        {paperState?.one_wv_usdt ?? "null"} | currentPaperState=
        {currentPaperState ? "OK" : "NULL"} | active_limit_orders=
        {currentPaperState?.active_limit_orders.length ?? "null"}
      </div>
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
          activeLimitOrders={
            currentPaperState?.ok ? currentPaperState.active_limit_orders : []
          }
          pendingLimitDraft={limitDraftState.draft}
          pendingLimitDrafts={
            limitDraftState.drafts ??
            (limitDraftState.draft ? [limitDraftState.draft] : [])
          }
          onPendingLimitSelect={(draftId) =>
            dispatchLimitDraft({ type: "select", draftId })
          }
          onPendingLimitDismiss={(draftId) =>
            dispatchLimitDraft({ type: "dismiss", draftId })
          }
          onPendingLimitDismissAll={() =>
            dispatchLimitDraft({ type: "dismiss-all" })
          }
          onPendingLimitPriceChange={(price, draftId) =>
            dispatchLimitDraft({ type: "update-price", price, draftId })
          }
          onPendingLimitConfirm={submitLimitDraft}
          fastLimitActive={fastLimitIntent !== null}
          onFastLimitPriceSelect={createFastLimitDraft}
        />
        <aside className="market-sidecar" aria-label="Market depth and tape">
          <DomPanel
            book={market.book}
            centerPrice={ladderCenterPrice}
            onCenterPriceChange={setLadderCenterPrice}
            ownOrders={market.ownOrders}
          compression={domCompression}
          onCompressionChange={setDomCompression}
          fastLimitActive={fastLimitIntent !== null}
          onFastLimitPriceSelect={submitDomLimit}
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
          symbol={tradingSymbol}
          paperState={currentPaperState}
          activeLimitOrders={
            currentPaperState?.ok ? currentPaperState.active_limit_orders : []
          }
          refreshPaperState={refreshPaperState}
          sizingReferencePrice={sizingReferencePrice}
          authoritativeTickSize={
            market.tickSize === null ? null : String(market.tickSize)
          }
          limitDraftState={limitDraftState}
          dispatchLimitDraft={dispatchLimitDraft}
          onLimitDraftConfirm={submitLimitDraft}
          onFastLimitHoldChange={setFastLimitIntent}
          onPositionSideChange={setPositionSide}
          onPositionAverageEntryChange={setPositionAverageEntry}
        />
      </section>
    </main>
  );
}
