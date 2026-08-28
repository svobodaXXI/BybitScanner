import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { AccountMenu } from "../components/AccountMenu";
import { ChartPanel } from "../components/ChartPanel";
import { DomPanel } from "../components/DomPanel";
import { ModePanel, type WorkspaceMode } from "../components/ModePanel";
import { TapePanel } from "../components/TapePanel";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import type {
  LimitCommandRequest,
  PaperLimitAmendRequest,
  PaperLimitCancelRequest,
} from "../contracts/trading";
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
import { executePaperLimitAmend, executePaperLimitCancel, executePaperLimitCommand } from "../orders/paperLimitCommand";
import { projectPaperLimitOrders } from "../orders/paperLimitProjection";
import { isValidSelectedVolume, updateSelectedVolume } from "../orders/selectedVolume";
import {
  paperTradingStore,
  usePaperTrading,
} from "../paperTrading/paperTradingStore";

export function App() {
  const [mode, setMode] = useState<WorkspaceMode>("TERMINAL");
  const [accountOpen, setAccountOpen] = useState(false);
  const [domCompression, setDomCompression] = useState(3);
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("5m");
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
  const [ladderCenterPrice, setLadderCenterPrice] = useState<number | null>(
    null,
  );
  const market = useMarketData();
  const tradingSymbol = market.book.symbol;
  const { paperState, pendingActions } = usePaperTrading(tradingSymbol);
  const currentPaperState =
    paperState?.symbol === tradingSymbol ? paperState : null;
  useEffect(() => {
    if (!currentPaperState?.ok || selectedVolumeSymbol.current === tradingSymbol) return;
    selectedVolumeSymbol.current = tradingSymbol;
    setSelectedVolumes({ Buy: currentPaperState.one_wv_usdt, Sell: currentPaperState.one_wv_usdt });
  }, [currentPaperState, tradingSymbol]);
  const activeLimitOrders = currentPaperState?.ok
    ? currentPaperState.active_limit_orders
    : [];
  const domOwnOrders = useMemo(
    () => projectPaperLimitOrders(activeLimitOrders),
    [activeLimitOrders],
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
      volume: { unit: "usdt", amount: volumeUsdt },
      sizing_reference_price: sizingReferencePrice,
      limit_price: normalizedPrice,
      time_in_force: "GTC",
    };
    await paperTradingStore.runMutation(
      `CREATE_LIMIT:${request.client_action_id}`,
      async () => {
        try {
          await executePaperLimitCommand(request, {
            applyPaperState: paperTradingStore.applyPaperState,
          });
        } catch {
          await paperTradingStore.refresh();
        }
      },
    );
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
          onActiveLimitAmend={amendPaperLimit}
        />
        <aside className="market-sidecar" aria-label="Market depth and tape">
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
        />
      </section>
    </main>
  );
}
