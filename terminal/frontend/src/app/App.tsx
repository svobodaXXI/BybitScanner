import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DomPanel } from "../components/DomPanel";
import { ModePanel, type WorkspaceMode } from "../components/ModePanel";
import { TapePanel } from "../components/TapePanel";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import type {
  PaperLimitAmendRequest,
  PaperLimitCancelRequest,
} from "../contracts/trading";
import {
  DOM_ROW_HEIGHT_REM,
  DOM_VISIBLE_ROWS,
  type DomViewportGeometry,
  recommendedLadderCenter,
} from "../marketData/domProjection";
import type { ChartTimeframe } from "../marketData/timeframes";
import { setMarketSymbol, setMarketTimeframe, useMarketData } from "../marketData/useMarketData";
import { marketApiRoutes } from "../marketData/apiRoutes";
import { TelegramMiniAppBridge } from "../telegram/TelegramMiniAppBridge";
import {
  createLimitDraft,
  EMPTY_LIMIT_DRAFT_STATE,
  limitDraftReducer,
} from "../orders/limitDraft";
import { PaperLimitDraftSubmitController } from "../orders/limitDraftSubmission";
import { executePaperLimitAmend, executePaperLimitCancel } from "../orders/paperLimitCommand";
import {
  DomLimitPlacementController,
  normalizedPaperLimitCreatePrice,
  type PaperLimitCreateIntent,
} from "../orders/paperLimitCreate";
import { projectPaperLimitOrders } from "../orders/paperLimitProjection";
import { isValidSelectedVolume, updateSelectedVolume } from "../orders/selectedVolume";
import {
  paperTradingStore,
  usePaperTrading,
} from "../paperTrading/paperTradingStore";

export function App() {
  const [mode, setMode] = useState<WorkspaceMode>("TERMINAL");
  const [accountOpen, setAccountOpen] = useState(false);
  const [marketSidePanelOpen, setMarketSidePanelOpen] = useState(true);
  const [domCompression, setDomCompression] = useState(3);
  const [domViewportGeometry, setDomViewportGeometry] = useState<DomViewportGeometry>({
    visibleRows: DOM_VISIBLE_ROWS,
    rowHeightPx: DOM_ROW_HEIGHT_REM * 16,
    viewportHeightPx: DOM_ROW_HEIGHT_REM * 16 * DOM_VISIBLE_ROWS,
  });
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("5m");
  const [instruments, setInstruments] = useState<string[]>([]);
  const [positionSide, setPositionSide] = useState<"Long" | "Short" | "Flat">("Flat");
  const [positionAverageEntry, setPositionAverageEntry] = useState<number | null>(null);
  const [selectedVolumes, setSelectedVolumes] = useState({ Buy: "", Sell: "" });
  const selectedVolumeSymbol = useRef<string | null>(null);
  const [fastLimitIntent, setFastLimitIntent] = useState<{ side: "Buy" | "Sell" } | null>(null);
  const [limitDraftState, dispatchLimitDraft] = useReducer(
    limitDraftReducer,
    EMPTY_LIMIT_DRAFT_STATE,
  );
  const limitSubmitController = useRef(new PaperLimitDraftSubmitController());
  const domLimitController = useRef(new DomLimitPlacementController());
  const [ladderCenterPrice, setLadderCenterPrice] = useState<number | null>(
    null,
  );
  const market = useMarketData();
  const tradingSymbol = market.book.symbol;
  const { paperState, pendingActions } = usePaperTrading(tradingSymbol);
  const currentPaperState =
    paperState?.symbol === tradingSymbol ? paperState : null;
  useEffect(() => {
    const controller = new AbortController();
    void fetch(marketApiRoutes.instruments, { signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((payload: { instruments?: Array<{ symbol?: string }> }) => {
        setInstruments((payload.instruments ?? []).flatMap((item) =>
          typeof item.symbol === "string" ? [item.symbol] : []));
      })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  const switchWorkspaceSymbol = useCallback((nextSymbol: string) => {
    if (nextSymbol === tradingSymbol) return;
    setFastLimitIntent(null);
    dispatchLimitDraft({ type: "dismiss-all" });
    setLadderCenterPrice(null);
    setPositionSide("Flat");
    setPositionAverageEntry(null);
    setMarketSymbol(nextSymbol);
  }, [tradingSymbol]);
  useEffect(() => {
    if (!currentPaperState?.ok || selectedVolumeSymbol.current === tradingSymbol) return;
    selectedVolumeSymbol.current = tradingSymbol;
    setSelectedVolumes({ Buy: currentPaperState.one_wv_usdt, Sell: currentPaperState.one_wv_usdt });
  }, [currentPaperState, tradingSymbol]);
  const activeLimitOrders = currentPaperState?.ok
    ? currentPaperState.active_limit_orders
    : [];
  const domOwnOrders = useMemo(
    () => projectPaperLimitOrders(activeLimitOrders, tradingSymbol),
    [activeLimitOrders, tradingSymbol],
  );
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

  const refreshPaperState = paperTradingStore.refresh;

  useEffect(() => {
    if (mode === "TERMINAL") void refreshPaperState();
  }, [mode, refreshPaperState]);

  useEffect(() => {
    if (mode !== "TERMINAL") return;

    if (paperState?.ok && paperState.active_limit_orders.length === 0) return;
    const timer = window.setInterval(() => {
      void refreshPaperState();
    }, 2_000);

    return () => window.clearInterval(timer);
  }, [mode, paperState, refreshPaperState]);

  const changeTimeframe = (next: ChartTimeframe) => {
    setTimeframe(next);
    setMarketTimeframe(next);
  };

  const createFastLimitDraft = useCallback(
    (price: string) => {
      const volumeUsdt = fastLimitIntent ? selectedVolumes[fastLimitIntent.side] : "";
      if (
        !fastLimitIntent ||
        market.book.health !== "READY" ||
        market.tickSize === null ||
        !isValidSelectedVolume(volumeUsdt)
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
          volume: { unit: "usdt", amount: volumeUsdt },
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
      selectedVolumes,
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
    const volumeUsdt = selectedVolumes[draft.side];
    if (!isValidSelectedVolume(volumeUsdt)) return;
    const attempt = limitSubmitController.current.submit({
      ...draft,
      volume: { unit: "usdt", amount: volumeUsdt },
    }, {
      dispatch: dispatchLimitDraft,
      createClientActionId: () =>
        globalThis.crypto?.randomUUID?.() ?? `paper-limit-${Date.now()}`,
      applyPaperState: paperTradingStore.applyPaperState,
    });
    return paperTradingStore
      .runMutation(`CREATE_LIMIT:${attempt.clientActionId}`, () => attempt.promise)
      .then(() => undefined);
  }, [limitDraftState.draft, limitDraftState.drafts, selectedVolumes]);

  const submitDomLimit = useCallback(async (price: string) => {
    if (!fastLimitIntent || market.tickSize === null) return;
    const volumeUsdt = selectedVolumes[fastLimitIntent.side];
    if (!isValidSelectedVolume(volumeUsdt)) return;
    const intent: PaperLimitCreateIntent = {
      symbol: tradingSymbol,
      side: fastLimitIntent.side,
      volume: { unit: "usdt", amount: volumeUsdt },
      sizingReferencePrice,
      price,
      authoritativeTickSize: String(market.tickSize),
    };
    const normalizedPrice = normalizedPaperLimitCreatePrice(intent);
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
    const attempt = domLimitController.current.submit(intent, {
      createClientActionId: () =>
        globalThis.crypto?.randomUUID?.() ?? `paper-dom-limit-${Date.now()}`,
      applyPaperState: paperTradingStore.applyPaperState,
    });
    const outcome = await paperTradingStore.runMutation(
      `CREATE_LIMIT:${attempt.clientActionId}`,
      () => attempt.promise,
    );
    if (outcome.certainty === "ambiguous") {
      await paperTradingStore.refresh();
    }
  }, [
    bestAsk,
    bestBid,
    fastLimitIntent,
    market.tickSize,
    selectedVolumes,
    sizingReferencePrice,
    tradingSymbol,
  ]);

  const cancelPaperLimit = useCallback(async (orderId: string) => {
    const request: PaperLimitCancelRequest = {
      client_action_id: `paper-limit-cancel-${Date.now()}`,
      symbol: tradingSymbol,
      order_id: orderId,
    };
    return paperTradingStore.runMutation(`CANCEL_LIMIT:${orderId}`, async () => {
      try {
        return await executePaperLimitCancel(request, {
          applyPaperState: paperTradingStore.applyPaperState,
        });
      } catch (error) {
        await paperTradingStore.refresh();
        throw error;
      }
    });
  }, [tradingSymbol]);

  const amendPaperLimit = useCallback(async (orderId: string, price: string) => {
    const request: PaperLimitAmendRequest = {
      client_action_id: globalThis.crypto?.randomUUID?.() ?? `paper-limit-amend-${Date.now()}`,
      symbol: tradingSymbol,
      order_id: orderId,
      limit_price: price,
    };
    try {
      const result = await paperTradingStore.runMutation(`AMEND_LIMIT:${orderId}`, () =>
        executePaperLimitAmend(request, { applyPaperState: paperTradingStore.applyPaperState }),
      );
      if (result.status !== "completed") throw new Error(result.reason_code);
    } catch (error) {
      await paperTradingStore.refresh();
      throw error;
    }
  }, [tradingSymbol]);

  return (
    <main className="workspace-shell">
      <TelegramMiniAppBridge />
      <section className="workspace-grid" aria-label="Trading workspace">
        <div
          className={`workspace-market-row ${marketSidePanelOpen ? "side-panel-open" : "side-panel-closed"}`}
        >
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
          onActiveLimitAmend={amendPaperLimit}
          onActiveLimitCancel={cancelPaperLimit}
          workspaceControls={(
            <WorkspaceHeader
              instruments={instruments}
              onSymbolSelect={switchWorkspaceSymbol}
              symbol={market.book.symbol}
              timeframe={timeframe}
              onTimeframeChange={changeTimeframe}
            />
          )}
          />
          <button
            aria-expanded={marketSidePanelOpen}
            aria-label={`${marketSidePanelOpen ? "Hide" : "Show"} DOM and Smart Tape`}
            className="market-side-panel-toggle"
            onClick={() => setMarketSidePanelOpen((open) => !open)}
            title={`${marketSidePanelOpen ? "Hide" : "Show"} DOM and Smart Tape`}
            type="button"
          >
            {marketSidePanelOpen ? "›" : "‹"}
          </button>
          <aside
            aria-hidden={!marketSidePanelOpen}
            className={`market-sidecar workspace-side-panel${marketSidePanelOpen ? "" : " is-hidden"}`}
            aria-label="Market depth and tape"
          >
              <TapePanel
                book={market.book}
                centerPrice={ladderCenterPrice}
                trades={market.trades}
                positionSide={positionSide}
                averageEntryPrice={positionAverageEntry}
                currentPrice={liveMidPrice}
                compression={domCompression}
                viewportGeometry={domViewportGeometry}
              />
              <DomPanel
                book={market.book}
                centerPrice={ladderCenterPrice}
                onCenterPriceChange={setLadderCenterPrice}
                ownOrders={domOwnOrders}
                onOwnOrderCancel={(orderId) => {
                  void cancelPaperLimit(orderId).catch(() => {});
                }}
                compression={domCompression}
                onCompressionChange={setDomCompression}
                fastLimitActive={fastLimitIntent !== null}
                onFastLimitPriceSelect={submitDomLimit}
                onViewportGeometryChange={setDomViewportGeometry}
              />
          </aside>
        </div>
        <ModePanel
          mode={mode}
          onModeChange={setMode}
          symbol={tradingSymbol}
          paperState={currentPaperState}
          activeLimitOrders={
            activeLimitOrders
          }
          onLimitCancel={cancelPaperLimit}
          refreshPaperState={refreshPaperState}
          applyPaperState={paperTradingStore.applyPaperState}
          pendingActions={pendingActions}
          runPaperMutation={paperTradingStore.runMutation}
          sizingReferencePrice={sizingReferencePrice}
          authoritativeTickSize={
            market.tickSize === null ? null : String(market.tickSize)
          }
          limitDraftState={limitDraftState}
          dispatchLimitDraft={dispatchLimitDraft}
          onLimitDraftConfirm={submitLimitDraft}
          onFastLimitHoldChange={setFastLimitIntent}
          selectedVolumes={selectedVolumes}
          onSelectedVolumeChange={(side, value) =>
            setSelectedVolumes((current) => updateSelectedVolume(current, side, value))
          }
          onPositionSideChange={setPositionSide}
          onPositionAverageEntryChange={setPositionAverageEntry}
          onWorkspaceSymbolSelect={switchWorkspaceSymbol}
          accountOpen={accountOpen}
          onAccountToggle={() => setAccountOpen((open) => !open)}
        />
      </section>
    </main>
  );
}
