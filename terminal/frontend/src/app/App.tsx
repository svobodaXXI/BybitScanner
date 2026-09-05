import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { ChartPanel } from "../components/ChartPanel";
import { DomPanel } from "../components/DomPanel";
import { ModePanel, type WorkspaceMode } from "../components/ModePanel";
import { TapePanel } from "../components/TapePanel";
import { WorkspaceHeader } from "../components/WorkspaceHeader";
import {
  accountWorkspaceStore,
  useAccountWorkspace,
} from "../accountWorkspace/accountWorkspaceStore";
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
import {
  requestWorkspaceActivation,
  type WorkspaceSemanticFailure,
} from "../marketData/workspaceSwitch";
import { TelegramMiniAppBridge } from "../telegram/TelegramMiniAppBridge";
import {
  createLimitDraft,
  EMPTY_LIMIT_DRAFT_STATE,
  limitDraftReducer,
  normalizeLimitDraftPrice,
} from "../orders/limitDraft";
import {
  type LimitInteractionIntent,
  limitDraftVolumeUsdt,
  sideDraftVolumesValid,
} from "../orders/limitInteractionCore";
import { PaperLimitDraftSubmitController } from "../orders/limitDraftSubmission";
import { executePaperLimitAmend, executePaperLimitCancel } from "../orders/paperLimitCommand";
import {
  DomLimitPlacementController,
  normalizedPaperLimitCreatePrice,
  type PaperLimitCreateIntent,
} from "../orders/paperLimitCreate";
import { projectPaperLimitOrders } from "../orders/paperLimitProjection";
import {
  executeLiveLimitAmend,
  executeLiveLimitCancel,
  executeLiveLimitCreate,
  liveLimitCreateRequest,
  projectLiveLimitOrders,
} from "../orders/liveLimitCommand";
import { isValidSelectedVolume, updateSelectedVolume } from "../orders/selectedVolume";
import {
  authoritativeStopPrice,
  authoritativeTakePrice,
  paperStateNeedsPolling,
  shouldClearStopDraft,
  stopDraftReducer,
} from "../orders/stopDraft";
import {
  isImprovingStop,
  loadStopPreset,
  loadTakePreset,
  saveStopPreset,
  saveTakePreset,
  shouldCloseStopSettings,
  stopPriceFromPercent,
  takePriceFromPercent,
} from "../orders/stopPreset";
import {
  executePaperStopAmend,
  executePaperStopCreate,
  executePaperStopDelete,
  executePaperTakeAmend,
  executePaperTakeCreate,
  executePaperTakeDelete,
} from "../orders/paperStopCommand";
import {
  isSignalTakeProposalHandled,
  markSignalTakeProposalHandled,
  readScannerSignalContext,
  shouldClearSignalTakeProposal,
  signalTakeProposalPrice,
} from "../orders/signalTakeProposal";
import {
  domSelectionRequiresMarket,
  executePaperMarketCommand,
} from "../orders/paperMarketCommand";
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
  const [workspaceSwitchError, setWorkspaceSwitchError] = useState<WorkspaceSemanticFailure | null>(null);
  const workspaceSwitchAttempt = useRef(0);
  const [positionSide, setPositionSide] = useState<"Long" | "Short" | "Flat">("Flat");
  const [positionAverageEntry, setPositionAverageEntry] = useState<number | null>(null);
  const [selectedVolumes, setSelectedVolumes] = useState({ Buy: "", Sell: "" });
  const [limitSubmissionFeedback, setLimitSubmissionFeedback] = useState<string | null>(null);
  const selectedVolumeWorkspaceKey = useRef<string | null>(null);
  const [fastLimitIntent, setFastLimitIntent] = useState<LimitInteractionIntent | null>(null);
  const [limitDraftState, dispatchLimitDraft] = useReducer(
    limitDraftReducer,
    EMPTY_LIMIT_DRAFT_STATE,
  );
  const [stopDraft, dispatchStopDraft] = useReducer(stopDraftReducer, null);
  const [takeDraft, dispatchTakeDraft] = useReducer(stopDraftReducer, null);
  const [stopPresetPercent, setStopPresetPercent] = useState(loadStopPreset);
  const [takePresetPercent, setTakePresetPercent] = useState(loadTakePreset);
  const [scannerSignal] = useState(readScannerSignalContext);
  const [protectionSettings, setProtectionSettings] = useState<{
    leg: "STOP" | "TAKE"; symbol: string;
  } | null>(null);
  const limitSubmitController = useRef(new PaperLimitDraftSubmitController());
  const domLimitController = useRef(new DomLimitPlacementController());
  const liveLimitAttempts = useRef(new Map<string, Promise<unknown>>());
  const [ladderCenterPrice, setLadderCenterPrice] = useState<number | null>(
    null,
  );
  const market = useMarketData();
  const tradingSymbol = market.book.symbol;
  const { paperState, pendingActions } = usePaperTrading(tradingSymbol);
  const accountWorkspace = useAccountWorkspace(tradingSymbol);
  const accountProjection = accountWorkspace.projection;
  const mutationsAllowed = !accountWorkspace.switching
    && accountProjection?.provider === "PAPER"
    && accountProjection.environment === "PAPER"
    && accountProjection.status === "READY";
  const liveMarketAllowed = !accountWorkspace.switching
    && accountProjection?.provider === "BYBIT"
    && accountProjection.environment === "MAINNET"
    && accountProjection.status === "READY"
    && accountProjection.read_only === false
    && accountProjection.capabilities?.market === true;
  const liveLimitAllowed = !accountWorkspace.switching
    && accountProjection?.provider === "BYBIT"
    && accountProjection.environment === "MAINNET"
    && accountProjection.status === "READY"
    && accountProjection.read_only === false
    && accountProjection.capabilities?.limit === true;
  const currentLiveAuthority = useCallback(() => liveLimitAllowed && accountProjection ? {
    accountId: accountProjection.account_id,
    sessionGeneration: accountProjection.session_generation,
  } : null, [accountProjection, liveLimitAllowed]);
  useEffect(() => {
    liveLimitAttempts.current.clear();
    paperTradingStore.setAccountSession(
      mutationsAllowed ? accountProjection.account_id : null,
      mutationsAllowed ? accountProjection.session_generation : null,
    );
  }, [accountProjection, mutationsAllowed]);
  const applyPaperStateForSession = paperTradingStore.captureApplyPaperState();
  const currentPaperState =
    mutationsAllowed && paperState?.symbol === tradingSymbol ? paperState : null;
  useEffect(() => {
    if (mutationsAllowed) return;
    setFastLimitIntent(null);
    dispatchLimitDraft({ type: "dismiss-all" });
    dispatchStopDraft({ type: "clear" });
    dispatchTakeDraft({ type: "clear" });
    setProtectionSettings(null);
    setPositionSide("Flat");
    setPositionAverageEntry(null);
  }, [accountProjection?.account_id, accountProjection?.session_generation, mutationsAllowed]);
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
  const switchWorkspaceSymbol = useCallback(async (nextSymbol: string) => {
    if (nextSymbol === tradingSymbol) return;
    const attempt = ++workspaceSwitchAttempt.current;
    const result = await requestWorkspaceActivation(nextSymbol, marketApiRoutes.workspaceSymbol);
    if (attempt !== workspaceSwitchAttempt.current) return;
    if (!result.ok) {
      setWorkspaceSwitchError(result.error);
      return;
    }
    setWorkspaceSwitchError(null);
    setFastLimitIntent(null);
    dispatchLimitDraft({ type: "dismiss-all" });
    dispatchStopDraft({ type: "clear" });
    dispatchTakeDraft({ type: "clear" });
    setProtectionSettings(null);
    setLadderCenterPrice(null);
    setPositionSide("Flat");
    setPositionAverageEntry(null);
    setMarketSymbol(result.symbol, result.generation);
  }, [tradingSymbol]);
  useEffect(() => {
    const oneWvUsdt = accountProjection?.one_wv_usdt ?? currentPaperState?.one_wv_usdt ?? null;
    if (!accountProjection || !oneWvUsdt || !isValidSelectedVolume(oneWvUsdt)) return;
    const workspaceKey = `${accountProjection.account_id}:${accountProjection.session_generation}:${tradingSymbol}`;
    if (selectedVolumeWorkspaceKey.current === workspaceKey) return;
    selectedVolumeWorkspaceKey.current = workspaceKey;
    setSelectedVolumes({ Buy: oneWvUsdt, Sell: oneWvUsdt });
  }, [accountProjection, currentPaperState, tradingSymbol]);
  const activeLimitOrders = currentPaperState?.ok
    ? currentPaperState.active_limit_orders
    : liveLimitAllowed && accountProjection
      ? projectLiveLimitOrders(accountProjection.orders, tradingSymbol)
      : [];
  const activeStopPrice = authoritativeStopPrice(currentPaperState);
  const activeTakePrice = authoritativeTakePrice(currentPaperState);
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

    if (!paperStateNeedsPolling(paperState)) return;
    const timer = window.setInterval(() => {
      void refreshPaperState();
    }, 2_000);

    return () => window.clearInterval(timer);
  }, [mode, paperState, refreshPaperState]);

  useEffect(() => {
    if (shouldClearStopDraft(stopDraft, currentPaperState, tradingSymbol)) {
      dispatchStopDraft({ type: "clear" });
    }
    if (shouldClearStopDraft(takeDraft, currentPaperState, tradingSymbol)) {
      dispatchTakeDraft({ type: "clear" });
    }
    if (shouldCloseStopSettings(protectionSettings?.symbol ?? null, currentPaperState, tradingSymbol)) {
      setProtectionSettings(null);
    }
  }, [currentPaperState, protectionSettings, stopDraft, takeDraft, tradingSymbol]);

  useEffect(() => {
    if (takeDraft !== null || scannerSignal === null) return;
    const price = signalTakeProposalPrice({
      signal: scannerSignal,
      state: currentPaperState,
      activeTakePrice,
      presetPercent: takePresetPercent,
      tickSize: market.tickSize === null ? null : String(market.tickSize),
      workspaceSymbol: tradingSymbol,
      handled: isSignalTakeProposalHandled(scannerSignal.signalId),
    });
    if (price === null) return;
    dispatchTakeDraft({
      type: "begin-create",
      symbol: tradingSymbol,
      price,
      proposalSignalId: scannerSignal.signalId,
    });
  }, [activeTakePrice, currentPaperState, market.tickSize, scannerSignal, takeDraft, takePresetPercent, tradingSymbol]);

  useEffect(() => {
    if (
      scannerSignal !== null && activeTakePrice !== null &&
      scannerSignal.symbol === tradingSymbol
    ) {
      markSignalTakeProposalHandled(scannerSignal.signalId);
    }
  }, [activeTakePrice, scannerSignal, tradingSymbol]);

  useEffect(() => {
    if (!shouldClearSignalTakeProposal(
      takeDraft?.proposalSignalId, currentPaperState, tradingSymbol, activeTakePrice,
    )) return;
    dispatchTakeDraft({ type: "clear" });
  }, [activeTakePrice, currentPaperState, takeDraft?.proposalSignalId, tradingSymbol]);

  const dismissTakeDraft = useCallback(() => {
    if (takeDraft?.proposalSignalId) {
      markSignalTakeProposalHandled(takeDraft.proposalSignalId);
    }
    dispatchTakeDraft({ type: "clear" });
  }, [takeDraft]);

  useEffect(() => {
    if (!takeDraft?.proposalSignalId || takeDraft.status === "submitting") return;
    const dismissOutside = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest('[data-protection-leg="TAKE"]')) return;
      markSignalTakeProposalHandled(takeDraft.proposalSignalId!);
      dispatchTakeDraft({ type: "clear" });
    };
    document.addEventListener("pointerdown", dismissOutside, true);
    return () => document.removeEventListener("pointerdown", dismissOutside, true);
  }, [takeDraft]);

  const changeTimeframe = (next: ChartTimeframe) => {
    setTimeframe(next);
    setMarketTimeframe(next);
  };

  const createFastLimitDraft = useCallback(
    (price: string) => {
      if (!mutationsAllowed && !liveLimitAllowed) return;
      if (
        !fastLimitIntent ||
        market.book.health !== "READY" ||
        market.tickSize === null ||
        !isValidSelectedVolume(fastLimitIntent.volumeUsdt)
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
      mutationsAllowed,
      liveLimitAllowed,
      sizingReferencePrice,
      tradingSymbol,
    ],
  );

  const submitLimitDraft = useCallback((draftId?: string) => {
    if (!mutationsAllowed && !liveLimitAllowed) {
      setLimitSubmissionFeedback("Limit confirmation unavailable: account authority changed.");
      return;
    }
    const drafts =
      limitDraftState.drafts ??
      (limitDraftState.draft ? [limitDraftState.draft] : []);
    const draft = draftId
      ? drafts.find((candidate) => candidate.draftId === draftId) ?? null
      : limitDraftState.draft;
    if (!draft) {
      setLimitSubmissionFeedback("Limit confirmation unavailable: draft no longer exists.");
      return;
    }
    if (draft.status === "submitting" || draft.status === "ambiguous") return;
    const volumeUsdt = limitDraftVolumeUsdt(draft);
    if (!isValidSelectedVolume(volumeUsdt)) {
      setLimitSubmissionFeedback("Enter a positive USDT Limit volume before confirming.");
      return;
    }
    if (liveLimitAllowed) {
      const attemptKey = `CREATE_LIMIT:${draft.draftId}`;
      const existingAttempt = liveLimitAttempts.current.get(attemptKey);
      if (existingAttempt) return existingAttempt.then(() => undefined);
      const authority = currentLiveAuthority();
      const normalizedPrice = normalizeLimitDraftPrice(
        draft.price, draft.authoritativeTickSize, draft.side,
      );
      if (!authority || normalizedPrice === null) {
        setLimitSubmissionFeedback("Limit confirmation unavailable: refresh the account or correct the price.");
        return;
      }
      setLimitSubmissionFeedback(null);
      const clientActionId = globalThis.crypto?.randomUUID?.() ?? `live-limit-${Date.now()}`;
      dispatchLimitDraft({ type: "start-submitting", clientActionId, draftId: draft.draftId });
      const liveAttempt = executeLiveLimitCreate(liveLimitCreateRequest({
        authority, clientActionId, symbol: draft.symbol, side: draft.side,
        volume: { unit: "usdt", amount: volumeUsdt },
        sizingReferencePrice: draft.sizingReferencePrice, limitPrice: normalizedPrice,
      }), currentLiveAuthority).then(async (result) => {
        if (result === null) return;
        if (result.status === "accepted_pending" || result.status === "completed") {
          dispatchLimitDraft({ type: "dismiss", draftId: draft.draftId });
          await accountWorkspaceStore.refreshActiveLive();
          liveLimitAttempts.current.delete(attemptKey);
        } else if (result.status === "unknown" || result.reconciliation_required) {
          dispatchLimitDraft({ type: "mark-ambiguous", clientActionId, draftId: draft.draftId });
        } else {
          dispatchLimitDraft({ type: "mark-rejected", clientActionId, reason: result.reason_code, draftId: draft.draftId });
          liveLimitAttempts.current.delete(attemptKey);
        }
      }).catch(() => {
        dispatchLimitDraft({ type: "mark-ambiguous", clientActionId, draftId: draft.draftId });
      });
      liveLimitAttempts.current.set(attemptKey, liveAttempt);
      return liveAttempt;
    }
    setLimitSubmissionFeedback(null);
    const attempt = limitSubmitController.current.submit(draft, {
      dispatch: dispatchLimitDraft,
      createClientActionId: () =>
        globalThis.crypto?.randomUUID?.() ?? `paper-limit-${Date.now()}`,
      applyPaperState: applyPaperStateForSession,
    });
    return paperTradingStore
      .runMutation(`CREATE_LIMIT:${attempt.clientActionId}`, () => attempt.promise)
      .then(() => undefined);
  }, [accountWorkspace, currentLiveAuthority, limitDraftState.draft, limitDraftState.drafts, liveLimitAllowed, mutationsAllowed]);

  const submitDomLimit = useCallback(async (price: string) => {
    if (!mutationsAllowed) return;
    if (!fastLimitIntent || market.tickSize === null) return;
    const volumeUsdt = fastLimitIntent.volumeUsdt;
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
    if (
      bestBid === undefined ||
      bestAsk === undefined
    ) {
      return;
    }

    if (
      domSelectionRequiresMarket(
        fastLimitIntent.side,
        normalizedPrice,
        bestBid,
        bestAsk,
      )
    ) {
      const side = fastLimitIntent.side;
      await paperTradingStore.runMutation(`MARKET:${side}`, async () => {
        try {
          await executePaperMarketCommand(
            {
              client_action_id:
                globalThis.crypto?.randomUUID?.() ??
                `paper-dom-market-${side.toLowerCase()}-${Date.now()}`,
              symbol: tradingSymbol,
              side,
              volume: { unit: "usdt", amount: volumeUsdt },
              sizing_reference_price: sizingReferencePrice,
              slippage_type: "Percent",
              slippage_value: "0.5",
            },
            { applyPaperState: applyPaperStateForSession },
          );
        } catch {
          await paperTradingStore.refresh();
        }
      });
      return;
    }

    const attempt = domLimitController.current.submit(intent, {
      createClientActionId: () =>
        globalThis.crypto?.randomUUID?.() ?? `paper-dom-limit-${Date.now()}`,
      applyPaperState: applyPaperStateForSession,
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
    mutationsAllowed,
    sizingReferencePrice,
    tradingSymbol,
  ]);

  const cancelPaperLimit = useCallback(async (orderId: string) => {
    if (!mutationsAllowed && !liveLimitAllowed) throw new Error("live_mutations_disabled");
    if (liveLimitAllowed) {
      const attemptKey = `CANCEL_LIMIT:${orderId}`;
      const existingAttempt = liveLimitAttempts.current.get(attemptKey);
      if (existingAttempt) return existingAttempt as Promise<never>;
      const authority = currentLiveAuthority();
      if (!authority) throw new Error("stale_live_authority");
      const liveAttempt = executeLiveLimitCancel({
        client_action_id: globalThis.crypto?.randomUUID?.() ?? `live-limit-cancel-${Date.now()}`,
        account_id: authority.accountId, session_generation: authority.sessionGeneration,
        symbol: tradingSymbol, order_id: orderId,
      }, currentLiveAuthority);
      liveLimitAttempts.current.set(attemptKey, liveAttempt);
      const result = await liveAttempt;
      if (result?.status === "accepted_pending" || result?.status === "completed") {
        await accountWorkspaceStore.refreshActiveLive();
        liveLimitAttempts.current.delete(attemptKey);
      } else if (result && result.status !== "unknown" && !result.reconciliation_required) {
        liveLimitAttempts.current.delete(attemptKey);
      }
      return result;
    }
    const request: PaperLimitCancelRequest = {
      client_action_id: `paper-limit-cancel-${Date.now()}`,
      symbol: tradingSymbol,
      order_id: orderId,
    };
    return paperTradingStore.runMutation(`CANCEL_LIMIT:${orderId}`, async () => {
      try {
        return await executePaperLimitCancel(request, {
          applyPaperState: applyPaperStateForSession,
        });
      } catch (error) {
        await paperTradingStore.refresh();
        throw error;
      }
    });
  }, [accountWorkspace, currentLiveAuthority, liveLimitAllowed, mutationsAllowed, tradingSymbol]);

  const amendPaperLimit = useCallback(async (orderId: string, price: string) => {
    if (!mutationsAllowed && !liveLimitAllowed) throw new Error("live_mutations_disabled");
    if (liveLimitAllowed) {
      const attemptKey = `AMEND_LIMIT:${orderId}`;
      const existingAttempt = liveLimitAttempts.current.get(attemptKey);
      if (existingAttempt) return existingAttempt.then(() => undefined);
      const authority = currentLiveAuthority();
      if (!authority) throw new Error("stale_live_authority");
      const liveAttempt = executeLiveLimitAmend({
        client_action_id: globalThis.crypto?.randomUUID?.() ?? `live-limit-amend-${Date.now()}`,
        account_id: authority.accountId, session_generation: authority.sessionGeneration,
        symbol: tradingSymbol, order_id: orderId, limit_price: price,
      }, currentLiveAuthority);
      liveLimitAttempts.current.set(attemptKey, liveAttempt);
      const result = await liveAttempt;
      if (result?.status !== "accepted_pending" && result?.status !== "completed") {
        if (result && result.status !== "unknown" && !result.reconciliation_required) {
          liveLimitAttempts.current.delete(attemptKey);
        }
        throw new Error(result?.reason_code ?? "stale_live_authority");
      }
      await accountWorkspaceStore.refreshActiveLive();
      liveLimitAttempts.current.delete(attemptKey);
      return;
    }
    const request: PaperLimitAmendRequest = {
      client_action_id: globalThis.crypto?.randomUUID?.() ?? `paper-limit-amend-${Date.now()}`,
      symbol: tradingSymbol,
      order_id: orderId,
      limit_price: price,
    };
    try {
      const result = await paperTradingStore.runMutation(`AMEND_LIMIT:${orderId}`, () =>
        executePaperLimitAmend(request, { applyPaperState: applyPaperStateForSession }),
      );
      if (result.status !== "completed") throw new Error(result.reason_code);
    } catch (error) {
      await paperTradingStore.refresh();
      throw error;
    }
  }, [accountWorkspace, currentLiveAuthority, liveLimitAllowed, mutationsAllowed, tradingSymbol]);

  const beginStopDraft = useCallback((): "drafted" | "not-improved" | undefined => {
    if (!currentPaperState?.ok || market.tickSize === null) return;
    const referencePrice = activeStopPrice === null
      ? currentPaperState.average_entry
      : sizingReferencePrice;
    const price = stopPriceFromPercent(
      currentPaperState.position_side,
      referencePrice,
      stopPresetPercent,
      String(market.tickSize),
    );
    if (price === null) return;
    if (activeStopPrice === null) {
      dispatchStopDraft({ type: "begin-create", symbol: tradingSymbol, price });
      return "drafted";
    }
    if (!isImprovingStop(currentPaperState.position_side, price, activeStopPrice)) {
      return "not-improved";
    }
    dispatchStopDraft({
      type: "begin-edit",
      symbol: tradingSymbol,
      authoritativePrice: activeStopPrice,
    });
    dispatchStopDraft({ type: "update-price", price });
    return "drafted";
  }, [activeStopPrice, currentPaperState, market.tickSize, sizingReferencePrice, stopPresetPercent, tradingSymbol]);

  const applyStopSettings = useCallback((price: string, percent: string) => {
    if (!currentPaperState?.ok) return;
    setStopPresetPercent(percent);
    saveStopPreset(percent);
    if (activeStopPrice === null) {
      dispatchStopDraft({ type: "begin-create", symbol: tradingSymbol, price });
    } else {
      dispatchStopDraft({
        type: "begin-edit",
        symbol: tradingSymbol,
        authoritativePrice: activeStopPrice,
      });
      dispatchStopDraft({ type: "update-price", price });
    }
    setProtectionSettings(null);
  }, [activeStopPrice, currentPaperState, tradingSymbol]);

  const updateStopPreset = useCallback((percent: string) => {
    setStopPresetPercent(percent);
    saveStopPreset(percent);
  }, []);

  const beginTakeDraft = useCallback(() => {
    if (!currentPaperState?.ok || market.tickSize === null) return;
    const referencePrice = activeTakePrice === null
      ? currentPaperState.average_entry
      : sizingReferencePrice;
    const price = takePriceFromPercent(
      currentPaperState.position_side,
      referencePrice,
      takePresetPercent,
      String(market.tickSize),
    );
    if (price === null) return;
    if (activeTakePrice === null) {
      dispatchTakeDraft({ type: "begin-create", symbol: tradingSymbol, price });
    } else {
      dispatchTakeDraft({
        type: "begin-edit", symbol: tradingSymbol,
        authoritativePrice: activeTakePrice,
      });
      dispatchTakeDraft({ type: "update-price", price });
    }
  }, [activeTakePrice, currentPaperState, market.tickSize, sizingReferencePrice, takePresetPercent, tradingSymbol]);

  const applyTakeSettings = useCallback((price: string, percent: string) => {
    if (!currentPaperState?.ok) return;
    setTakePresetPercent(percent);
    saveTakePreset(percent);
    if (activeTakePrice === null) {
      dispatchTakeDraft({ type: "begin-create", symbol: tradingSymbol, price });
    } else {
      dispatchTakeDraft({
        type: "begin-edit", symbol: tradingSymbol,
        authoritativePrice: activeTakePrice,
      });
      dispatchTakeDraft({ type: "update-price", price });
    }
    setProtectionSettings(null);
  }, [activeTakePrice, currentPaperState, tradingSymbol]);

  const updateTakePreset = useCallback((percent: string) => {
    setTakePresetPercent(percent);
    saveTakePreset(percent);
  }, []);

  const beginStopEdit = useCallback(() => {
    if (activeStopPrice === null) return;
    dispatchStopDraft({
      type: "begin-edit",
      symbol: tradingSymbol,
      authoritativePrice: activeStopPrice,
    });
  }, [activeStopPrice, tradingSymbol]);

  const beginTakeEdit = useCallback(() => {
    if (activeTakePrice === null) return;
    dispatchTakeDraft({
      type: "begin-edit", symbol: tradingSymbol,
      authoritativePrice: activeTakePrice,
    });
  }, [activeTakePrice, tradingSymbol]);

  const updateStopDraftPrice = useCallback((rawPrice: string) => {
    if (!stopDraft || !currentPaperState?.ok || market.tickSize === null) return;
    const closingSide = currentPaperState.position_side === "Long" ? "Sell" : "Buy";
    const normalized = normalizeLimitDraftPrice(
      rawPrice, String(market.tickSize), closingSide,
    );
    if (normalized !== null) {
      dispatchStopDraft({ type: "update-price", price: normalized });
    }
  }, [currentPaperState, market.tickSize, stopDraft]);

  const updateTakeDraftPrice = useCallback((rawPrice: string) => {
    if (!takeDraft || !currentPaperState?.ok || market.tickSize === null) return;
    const closingSide = currentPaperState.position_side === "Long" ? "Sell" : "Buy";
    const normalized = normalizeLimitDraftPrice(rawPrice, String(market.tickSize), closingSide);
    if (normalized !== null) dispatchTakeDraft({ type: "update-price", price: normalized });
  }, [currentPaperState, market.tickSize, takeDraft]);

  const confirmProtectionDraft = useCallback(async (leg: "STOP" | "TAKE") => {
    const draft = leg === "STOP" ? stopDraft : takeDraft;
    const dispatch = leg === "STOP" ? dispatchStopDraft : dispatchTakeDraft;
    if (!draft || draft.status === "submitting") return;
    const clientActionId = globalThis.crypto?.randomUUID?.()
      ?? `paper-${leg.toLowerCase()}-${Date.now()}`;
    dispatch({ type: "submitting" });
    try {
      const execute = leg === "STOP"
        ? draft.mode === "CREATE" ? executePaperStopCreate : executePaperStopAmend
        : draft.mode === "CREATE" ? executePaperTakeCreate : executePaperTakeAmend;
      const result = await paperTradingStore.runMutation(
        `${draft.mode}_${leg}:${clientActionId}`,
        () => execute({
          client_action_id: clientActionId,
          symbol: tradingSymbol,
          trigger_price: draft.price,
        }, { applyPaperState: applyPaperStateForSession }),
      );
      const authoritative = leg === "STOP"
        ? authoritativeStopPrice(result.paper_state)
        : authoritativeTakePrice(result.paper_state);
      if (authoritative !== null) {
        if (leg === "TAKE" && draft.proposalSignalId) {
          markSignalTakeProposalHandled(draft.proposalSignalId);
        }
        dispatch({ type: "clear" });
      } else {
        dispatch({ type: "restore-editing" });
      }
    } catch {
      dispatch({ type: "restore-editing" });
      await paperTradingStore.refresh();
    }
  }, [stopDraft, takeDraft, tradingSymbol]);

  const deleteProtection = useCallback(async (leg: "STOP" | "TAKE") => {
    if ((leg === "STOP" ? activeStopPrice : activeTakePrice) === null) return;
    const clientActionId = globalThis.crypto?.randomUUID?.()
      ?? `paper-${leg.toLowerCase()}-delete-${Date.now()}`;
    const execute = leg === "STOP" ? executePaperStopDelete : executePaperTakeDelete;
    try {
      await paperTradingStore.runMutation(`DELETE_${leg}:${clientActionId}`, () =>
        execute({
          client_action_id: clientActionId,
          symbol: tradingSymbol,
        }, { applyPaperState: applyPaperStateForSession }),
      );
    } catch {
      await paperTradingStore.refresh();
    }
  }, [activeStopPrice, activeTakePrice, tradingSymbol]);

  const visibleLimitDrafts =
    limitDraftState.drafts ??
    (limitDraftState.draft ? [limitDraftState.draft] : []);

  return (
    <main className="workspace-shell">
      {workspaceSwitchError && (
        <output
          aria-live="polite"
          data-error-code={workspaceSwitchError.code}
          data-error-stage={workspaceSwitchError.stage}
          role="alert"
        >
          {workspaceSwitchError.message}
        </output>
      )}
      {limitSubmissionFeedback && (
        <output aria-live="polite" role="status">
          {limitSubmissionFeedback}
        </output>
      )}
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
          liveLimitDrafts={accountProjection?.provider === "BYBIT"}
          pendingLimitDrafts={visibleLimitDrafts}
          pendingLimitVolumeValid={{
            Buy: sideDraftVolumesValid(visibleLimitDrafts, "Buy", selectedVolumes.Buy),
            Sell: sideDraftVolumesValid(visibleLimitDrafts, "Sell", selectedVolumes.Sell),
          }}
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
          authoritativeStopPrice={activeStopPrice}
          stopDraft={stopDraft}
          onStopDraftPriceChange={updateStopDraftPrice}
          onStopConfirm={() => confirmProtectionDraft("STOP")}
          onStopCancelDraft={() => dispatchStopDraft({ type: "clear" })}
          onStopEdit={beginStopEdit}
          onStopDelete={() => deleteProtection("STOP")}
          authoritativeTakePrice={activeTakePrice}
          takeDraft={takeDraft}
          onTakeDraftPriceChange={updateTakeDraftPrice}
          onTakeConfirm={() => confirmProtectionDraft("TAKE")}
          onTakeCancelDraft={dismissTakeDraft}
          onTakeEdit={beginTakeEdit}
          onTakeDelete={() => deleteProtection("TAKE")}
          averageEntryPrice={
            currentPaperState?.ok && currentPaperState.position_side !== "Flat"
              ? currentPaperState.average_entry
              : null
          }
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
          applyPaperState={applyPaperStateForSession}
          pendingActions={pendingActions}
          runPaperMutation={paperTradingStore.runMutation}
          sizingReferencePrice={sizingReferencePrice}
          authoritativeTickSize={
            market.tickSize === null ? null : String(market.tickSize)
          }
          limitDraftState={limitDraftState}
          dispatchLimitDraft={dispatchLimitDraft}
          onLimitDraftConfirm={submitLimitDraft}
          onFastLimitHoldChange={(intent) =>
            setFastLimitIntent(intent ? { ...intent, origin: "chart-fast" } : null)
          }
          selectedVolumes={selectedVolumes}
          onSelectedVolumeChange={(side, value) => {
            setSelectedVolumes((current) => updateSelectedVolume(current, side, value));
            const popupDraft = visibleLimitDrafts.find(
              (draft) => draft.origin === "limits-popup" && draft.side === side,
            );
            if (popupDraft) {
              dispatchLimitDraft({
                type: "update-volume",
                draftId: popupDraft.draftId,
                volume: { unit: "usdt", amount: value },
              });
            }
          }}
          onPositionSideChange={setPositionSide}
          onPositionAverageEntryChange={setPositionAverageEntry}
          onStopTap={beginStopDraft}
          onStopHold={() => setProtectionSettings({ leg: "STOP", symbol: tradingSymbol })}
          stopActive={activeStopPrice !== null}
          stopSettingsOpen={protectionSettings?.leg === "STOP" && protectionSettings.symbol === tradingSymbol}
          stopPresetPercent={stopPresetPercent}
          stopReferencePrice={
            activeStopPrice === null
              ? currentPaperState?.average_entry ?? "0"
              : sizingReferencePrice
          }
          onStopSettingsApply={applyStopSettings}
          onStopPresetChange={updateStopPreset}
          onStopSettingsClose={() => setProtectionSettings(null)}
          onTakeTap={beginTakeDraft}
          onTakeHold={() => setProtectionSettings({ leg: "TAKE", symbol: tradingSymbol })}
          takeActive={activeTakePrice !== null}
          takeSettingsOpen={protectionSettings?.leg === "TAKE" && protectionSettings.symbol === tradingSymbol}
          takePresetPercent={takePresetPercent}
          takeReferencePrice={
            activeTakePrice === null
              ? currentPaperState?.average_entry ?? "0"
              : sizingReferencePrice
          }
          onTakeSettingsApply={applyTakeSettings}
          onTakePresetChange={updateTakePreset}
          onTakeSettingsClose={() => setProtectionSettings(null)}
          onWorkspaceSymbolSelect={switchWorkspaceSymbol}
          accountOpen={accountOpen}
          onAccountToggle={() => setAccountOpen((open) => !open)}
          accountWorkspaceProjection={accountProjection}
          mutationsAllowed={mutationsAllowed}
          liveMarketAllowed={liveMarketAllowed}
          liveLimitAllowed={liveLimitAllowed}
        />
      </section>
    </main>
  );
}
