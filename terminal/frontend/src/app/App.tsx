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
import { parseSignalWorkspaceLink } from "../geometryFeedback/signalDeepLink";
import { appendRetrospectiveCandles, projectSignalGeometry, restoreSavedSignalCorrection, type RetrospectiveOhlc } from "../geometryFeedback/signalChartBridge";
import type { OwnerSignalDraft } from "../geometryFeedback/ownerSignalDraft";
import { matchesStoredGeometryReview, type GeometryReviewDraft, type TimestampDrawing } from "../geometryFeedback/geometryReviewDraft";
import type { Candle } from "../contracts/marketData";
import type { PaperOpenPosition } from "../contracts/trading";
import type { RobotTradeMarker } from "../chart/robotTradeMarkers";
import type { DrawingObject } from "../chart/drawingModel";
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
import { LiveLimitDraftSubmitController } from "../orders/liveLimitDraftSubmission";
import {
  LiveLimitOrderMutationController,
  PaperLimitOrderMutationController,
} from "../orders/limitOrderMutationSubmission";
import {
  DomLimitPlacementController,
  normalizedPaperLimitCreatePrice,
  type PaperLimitCreateIntent,
} from "../orders/paperLimitCreate";
import { projectPaperLimitOrders } from "../orders/paperLimitProjection";
import { projectLiveLimitOrders } from "../orders/liveLimitCommand";
import { isValidSelectedVolume, updateSelectedVolume } from "../orders/selectedVolume";
import {
  authoritativeStopPrice,
  authoritativeTakePrice,
  paperStateNeedsPolling,
  shouldClearStopDraft,
  stopDraftReducer,
} from "../orders/stopDraft";
import {
  loadStopPreset,
  loadTakePreset,
  protectionPercentFromPrice,
  saveStopPreset,
  saveTakePreset,
  shouldCloseStopSettings,
  stopPriceFromPercent,
  takePriceFromPercent,
} from "../orders/stopPreset";
import { PaperProtectionMutationController } from "../orders/paperProtectionMutationSubmission";
import { LiveProtectionMutationController } from "../orders/liveProtectionMutationSubmission";
import { projectLiveProtectionPosition } from "../orders/liveProtectionProjection";
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

const sameProtectionPrice = (left: string | null, right: string | null) => {
  if (left === null || right === null) return left === right;
  const a = Number(left);
  const b = Number(right);
  return Number.isFinite(a) && Number.isFinite(b) && a === b;
};

export function App() {
  const launchLink = useMemo(() => parseSignalWorkspaceLink(window.location.search), []);
  // A signal-specific Telegram "Терминал" link opens Robot observation;
  // a plain Terminal link without a source identity stays manual.
  const [mode, setMode] = useState<WorkspaceMode>(
    launchLink?.mode === "TERMINAL" && launchLink.signalId ? "AUTOPILOT" : launchLink?.mode ?? "TERMINAL",
  );
  const [robotPositions, setRobotPositions] = useState<PaperOpenPosition[] | null>(null);
  const [robotMarkers, setRobotMarkers] = useState<{
    symbol: string; tradeId: string; markers: RobotTradeMarker[];
  } | null>(null);
  const [frozenSignal, setFrozenSignal] = useState<{
    candles: Candle[];
    sourceCandles: Candle[];
    sourceBoundaries: TimestampDrawing[];
    context: { asOfMs: number; barsSha256: string } | null;
    referenceDrawings: DrawingObject[];
    editableDrawings: DrawingObject[];
    signalId: string;
    originalPattern: string | null;
    snapshotRevision: string;
    barsSha256: string;
    savedReviewId: string | null;
    savedReviewLabel: GeometryReviewDraft["label"] | null;
    savedReviewNote: string | null;
  } | null>(null);
  const [frozenGeometryStatus, setFrozenGeometryStatus] = useState<"loading" | "unavailable" | "ready">("loading");
  useEffect(() => {
    const link = launchLink;
    if (!link || !link.signalId) return;
    const controller = new AbortController();
    const load = async () => {
      try {
        const response = await fetch(
          `/api/workspace/signal-geometry?signal_id=${encodeURIComponent(link.signalId!)}`,
          { signal: controller.signal, credentials: "same-origin" },
        );
        if (!response.ok) throw new Error("Source snapshot not found");
        const payload = await response.json();
        const snapshot = payload.snapshot;
        const expectedTimeframe = ({ "15s": "15s", "1m": "1", "5m": "5", "15m": "15", "1h": "60", "1d": "D" } as Record<string, string>)[link.timeframe];
        if (!payload.ok || !snapshot || snapshot.signal_id !== link.signalId ||
            snapshot.symbol !== link.symbol || String(snapshot.timeframe) !== expectedTimeframe)
          throw new Error("Source identity mismatch");
        if (!Array.isArray(snapshot.bars) || !Array.isArray(snapshot.boundaries))
          throw new Error("Incomplete immutable geometry");
        const candles: Candle[] = snapshot.bars.map((bar: {
          open_time_ms: number; open: number; high: number; low: number; close: number;
        }) => ({
          time: new Date(bar.open_time_ms).toISOString(),
          open: bar.open, high: bar.high, low: bar.low, close: bar.close,
        }));
        const boundaries: TimestampDrawing[] = snapshot.boundaries.map((line: {
          boundary_id: string; kind: "ray" | "segment" | "horizontal" | "horizontal-ray";
          anchors: { bar_open_time_ms: number; price: number }[];
        }) => ({ id: line.boundary_id, type: line.kind, anchors: line.anchors }));
        const projected = projectSignalGeometry(boundaries, candles);
        if (typeof payload.snapshot_revision !== "string" || !/^[0-9a-f]{64}$/i.test(payload.snapshot_revision)
            || typeof payload.bars_sha256 !== "string" || !/^[0-9a-f]{64}$/i.test(payload.bars_sha256))
          throw new Error("Frozen snapshot provenance is unavailable");
        const savedReview = payload.latest_review as {
          review_id?: string;
          retrospective_bars?: RetrospectiveOhlc[];
          submission?: {
            context_as_of_ms?: number;
            context_bars_sha256?: string;
            signal_id?: string; snapshot_revision?: string; bars_sha256?: string;
            label?: GeometryReviewDraft["label"]; note?: string;
            corrected_boundaries?: Array<{
              boundary_id: string; kind: TimestampDrawing["type"]; anchors: TimestampDrawing["anchors"];
            }>;
          };
        } | null;
        const savedReviewLabel = savedReview?.submission?.label ?? null;
        if (savedReview && (
          typeof savedReview.review_id !== "string"
          || !/^[0-9a-f]{64}$/i.test(savedReview.review_id)
          || savedReview.submission?.signal_id !== link.signalId
          || savedReview.submission?.snapshot_revision !== payload.snapshot_revision
          || savedReview.submission?.bars_sha256 !== payload.bars_sha256
          || !["CONFIRMED", "GEOMETRY_CORRECTED", "FALSE_POSITIVE", "UNCERTAIN"].includes(savedReviewLabel ?? "")
          || typeof savedReview.submission?.note !== "string"
          || savedReview.submission.note.length > 1024
        )) throw new Error("Saved review does not match source signal");
        const savedContext = savedReview?.submission?.context_as_of_ms !== undefined
          ? {
              asOfMs: savedReview.submission.context_as_of_ms,
              barsSha256: savedReview.submission.context_bars_sha256 ?? "",
            }
          : null;
        if ((savedContext && (!/^[0-9a-f]{64}$/i.test(savedContext.barsSha256) ||
              !Array.isArray(savedReview?.retrospective_bars))) ||
            (!savedContext && savedReview?.retrospective_bars))
          throw new Error("Invalid saved retrospective context");
        const reviewCandles = savedContext
          ? appendRetrospectiveCandles(
              candles, savedReview?.retrospective_bars ?? [],
              snapshot.timeframe, savedContext.asOfMs,
            )
          : candles;
        let editableDrawings = projected.editableDrawings;
        if (savedReviewLabel === "GEOMETRY_CORRECTED") {
          if (!Array.isArray(savedReview?.submission?.corrected_boundaries))
            throw new Error("Saved correction does not match source signal");
          const reviewedLines: TimestampDrawing[] = savedReview.submission.corrected_boundaries.map((line) => ({
            id: line.boundary_id, type: line.kind, anchors: line.anchors,
          }));
          editableDrawings = restoreSavedSignalCorrection(
            projected.referenceDrawings, reviewedLines, reviewCandles,
          );
        }
        if (!controller.signal.aborted) {
          setFrozenSignal({
            candles: reviewCandles, sourceCandles: candles,
            sourceBoundaries: boundaries, context: savedContext,
            ...projected, editableDrawings, signalId: link.signalId!,
            originalPattern: typeof payload.original_pattern === "string" && payload.original_pattern.trim()
              ? payload.original_pattern.trim() : null,
            snapshotRevision: payload.snapshot_revision, barsSha256: payload.bars_sha256,
            savedReviewId: typeof savedReview?.review_id === "string" ? savedReview.review_id : null,
            savedReviewLabel,
            savedReviewNote: savedReview?.submission?.note ?? null,
          });
          setFrozenGeometryStatus("ready");
        }
      } catch {
        // No live-candle refit or symbol-only fallback for missing source lines.
        if (!controller.signal.aborted) setFrozenGeometryStatus("unavailable");
      }
    };
    void load();
    return () => controller.abort();
  }, [launchLink]);
  const [accountOpen, setAccountOpen] = useState(false);
  const [marketSidePanelOpen, setMarketSidePanelOpen] = useState(true);
  const [domCompression, setDomCompression] = useState(3);
  const [domViewportGeometry, setDomViewportGeometry] = useState<DomViewportGeometry>({
    visibleRows: DOM_VISIBLE_ROWS,
    rowHeightPx: DOM_ROW_HEIGHT_REM * 16,
    viewportHeightPx: DOM_ROW_HEIGHT_REM * 16 * DOM_VISIBLE_ROWS,
  });
  const [timeframe, setTimeframe] = useState<ChartTimeframe>(launchLink?.timeframe ?? "5m");
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
  const liveLimitSubmitController = useRef(new LiveLimitDraftSubmitController());
  const paperLimitOrderMutationController = useRef(new PaperLimitOrderMutationController());
  const liveLimitOrderMutationController = useRef(new LiveLimitOrderMutationController());
  const paperProtectionMutationController = useRef(new PaperProtectionMutationController());
  const liveProtectionMutationController = useRef(new LiveProtectionMutationController());
  const limitMutationAuthorityKey = useRef<string | null>(null);
  const protectionMutationAuthorityKey = useRef<string | null>(null);
  const domLimitController = useRef(new DomLimitPlacementController());
  const [ladderCenterPrice, setLadderCenterPrice] = useState<number | null>(
    null,
  );
  const market = useMarketData();
  const tradingSymbol = market.book.symbol;
  // Telegram signal provenance is independent of the selected PAPER/MAIN account.
  // Only draw exact frozen anchors on matching *current* candles, never on
  // an unrelated symbol/interval or an approximate historical bar.
  const terminalSignalDrawings = useMemo(() => {
    if ((mode !== "TERMINAL" && mode !== "AUTOPILOT") || launchLink?.mode !== "TERMINAL"
        || !launchLink.signalId || !frozenSignal
        || tradingSymbol !== launchLink.symbol || timeframe !== launchLink.timeframe)
      return null;
    try {
      return projectSignalGeometry(frozenSignal.sourceBoundaries, market.candles).referenceDrawings;
    } catch {
      return null; // Missing historical anchor: no fabricated live geometry.
    }
  }, [mode, launchLink, frozenSignal, tradingSymbol, timeframe, market.candles]);
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
  const liveProtectionAllowed = !accountWorkspace.switching
    && accountProjection?.provider === "BYBIT"
    && accountProjection.environment === "MAINNET"
    && accountProjection.status === "READY"
    && accountProjection.read_only === false
    && accountProjection.capabilities?.stop === true
    && accountProjection.capabilities?.take === true;
  const liveAuthoritySnapshot = useRef({
    projection: accountProjection,
    limitAllowed: liveLimitAllowed,
    protectionAllowed: liveProtectionAllowed,
  });
  liveAuthoritySnapshot.current = {
    projection: accountProjection,
    limitAllowed: liveLimitAllowed,
    protectionAllowed: liveProtectionAllowed,
  };
  const currentLiveAuthority = useCallback(() => {
    const current = liveAuthoritySnapshot.current;
    return current.limitAllowed && current.projection ? {
      accountId: current.projection.account_id,
      sessionGeneration: current.projection.session_generation,
    } : null;
  }, []);
  const currentLiveProtectionAuthority = useCallback(() => {
    const current = liveAuthoritySnapshot.current;
    return current.protectionAllowed && current.projection ? {
      accountId: current.projection.account_id,
      sessionGeneration: current.projection.session_generation,
    } : null;
  }, []);
  useEffect(() => {
    const nextMutationAuthorityKey = liveLimitAllowed && accountProjection
      ? `LIVE:${accountProjection.account_id}:${accountProjection.session_generation}`
      : mutationsAllowed && accountProjection
        ? `PAPER:${accountProjection.account_id}:${accountProjection.session_generation}`
        : null;
    if (limitMutationAuthorityKey.current !== nextMutationAuthorityKey) {
      limitMutationAuthorityKey.current = nextMutationAuthorityKey;
      paperLimitOrderMutationController.current.clear();
      liveLimitOrderMutationController.current.clear();
    }
    const nextProtectionAuthorityKey = liveProtectionAllowed && accountProjection
      ? `LIVE:${accountProjection.account_id}:${accountProjection.session_generation}`
      : mutationsAllowed && accountProjection
        ? `PAPER:${accountProjection.account_id}:${accountProjection.session_generation}`
        : null;
    if (protectionMutationAuthorityKey.current !== nextProtectionAuthorityKey) {
      protectionMutationAuthorityKey.current = nextProtectionAuthorityKey;
      paperProtectionMutationController.current.clear();
      liveProtectionMutationController.current.clear();
    }
    paperTradingStore.setAccountSession(
      mutationsAllowed ? accountProjection.account_id : null,
      mutationsAllowed ? accountProjection.session_generation : null,
    );
  }, [
    accountProjection?.account_id,
    accountProjection?.session_generation,
    liveLimitAllowed,
    liveProtectionAllowed,
    mutationsAllowed,
  ]);
  const applyPaperStateForSession = paperTradingStore.captureApplyPaperState();
  const currentPaperState =
    mutationsAllowed && paperState?.symbol === tradingSymbol ? paperState : null;
  // A Robot trade association alone is not enough: verify the live PAPER
  // projection agrees before labelling any position or its protection as Robot.
  const robotPosition = mode === "AUTOPILOT" && accountProjection?.provider === "PAPER" &&
    accountProjection.environment === "PAPER" && currentPaperState?.ok
    ? robotPositions?.find((p) =>
        p.symbol === tradingSymbol && typeof p.robot_trade_id === "string" && p.robot_trade_id.length > 0 &&
        p.position_side === currentPaperState.position_side &&
        Number.isFinite(Number(p.position_quantity)) && Number(p.position_quantity) > 0 &&
        Number(p.position_quantity) === Number(currentPaperState.position_quantity),
      ) ?? null
    : null;
  // Read-only snapshot of EXACTLY the same TradeMarkers used by Telegram
  // position cards. Never infer Robot executions from OHLC or generic Diary.
  const activeRobotTradeId = robotPosition?.robot_trade_id ?? null;
  useEffect(() => {
    setRobotMarkers(null);
    if (mode !== "AUTOPILOT" || !activeRobotTradeId || !robotPosition) return;
    const controller = new AbortController();
    const symbol = robotPosition.symbol, tradeId = activeRobotTradeId;
    void (async () => {
      try {
        const response = await fetch(
          `/api/robot/position-markers?symbol=${encodeURIComponent(symbol)}&trade_id=${encodeURIComponent(tradeId)}`,
          { signal: controller.signal },
        );
        if (!response.ok) return;
        const result = await response.json() as {
          ok?: boolean; account_id?: string; source?: string; symbol?: string;
          trade_id?: string; markers?: RobotTradeMarker[];
        };
        if (result.ok !== true || result.account_id !== "paper" ||
            result.source !== "robot_position_view.TradeMarker" ||
            result.symbol !== symbol || result.trade_id !== tradeId ||
            !Array.isArray(result.markers)) return;
        if (!controller.signal.aborted)
          setRobotMarkers({ symbol, tradeId, markers: result.markers });
      } catch {
        // Read-only observation only: unavailable evidence means no markers.
      }
    })();
    return () => controller.abort();
  }, [mode, activeRobotTradeId, robotPosition?.symbol]);

  const liveProtectionPosition = liveProtectionAllowed
    ? projectLiveProtectionPosition(accountProjection, tradingSymbol)
    : null;
  const protectionPositionSide = currentPaperState?.ok
    ? currentPaperState.position_side
    : liveProtectionPosition?.side ?? "Flat";
  const protectionAverageEntry = currentPaperState?.ok
    ? currentPaperState.average_entry
    : liveProtectionPosition?.averageEntry ?? null;
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
  const initialLinkConsumed = useRef(false);
  useEffect(() => {
    if (initialLinkConsumed.current || !launchLink) return;
    initialLinkConsumed.current = true;
    setMarketTimeframe(launchLink.timeframe);
    void switchWorkspaceSymbol(launchLink.symbol);
  }, [launchLink, switchWorkspaceSymbol]);
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
  const activeStopPrice = currentPaperState?.ok
    ? authoritativeStopPrice(currentPaperState)
    : liveProtectionPosition?.stopLoss ?? null;
  const activeTakePrice = currentPaperState?.ok
    ? authoritativeTakePrice(currentPaperState)
    : liveProtectionPosition?.takeProfit ?? null;
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
    if (mode === "TERMINAL" || (mode === "AUTOPILOT" && mutationsAllowed))
      void refreshPaperState();
  }, [mode, mutationsAllowed, refreshPaperState]);

  useEffect(() => {
    if (mode !== "TERMINAL" && (mode !== "AUTOPILOT" || !mutationsAllowed)) return;

    if (!paperStateNeedsPolling(paperState)) return;
    const timer = window.setInterval(() => {
      void refreshPaperState();
    }, 2_000);

    return () => window.clearInterval(timer);
  }, [mode, mutationsAllowed, paperState, refreshPaperState]);

  useEffect(() => {
    const protectionUnavailable = !mutationsAllowed && !liveProtectionAllowed;
    const clearForLive = liveProtectionAllowed && liveProtectionPosition === null;
    if (
      shouldClearStopDraft(stopDraft, currentPaperState, tradingSymbol)
      || (stopDraft !== null && (
        stopDraft.symbol !== tradingSymbol || clearForLive || protectionUnavailable
      ))
    ) {
      dispatchStopDraft({ type: "clear" });
    }
    if (
      shouldClearStopDraft(takeDraft, currentPaperState, tradingSymbol)
      || (takeDraft !== null && (
        takeDraft.symbol !== tradingSymbol || clearForLive || protectionUnavailable
      ))
    ) {
      dispatchTakeDraft({ type: "clear" });
    }
    const closePaperSettings = shouldCloseStopSettings(
      protectionSettings?.symbol ?? null, currentPaperState, tradingSymbol,
    );
    const closeLiveSettings = liveProtectionAllowed
      && protectionSettings !== null
      && (protectionSettings.symbol !== tradingSymbol || liveProtectionPosition === null);
    const closeUnavailableSettings = protectionUnavailable && protectionSettings !== null;
    if (closePaperSettings || closeLiveSettings || closeUnavailableSettings) {
      setProtectionSettings(null);
    }
  }, [
    currentPaperState,
    liveProtectionAllowed,
    liveProtectionPosition,
    mutationsAllowed,
    protectionSettings,
    stopDraft,
    takeDraft,
    tradingSymbol,
  ]);

  useEffect(() => {
    if (!liveProtectionAllowed) return;
    if (stopDraft?.status === "submitting" && sameProtectionPrice(activeStopPrice, stopDraft.price)) {
      dispatchStopDraft({ type: "clear" });
    }
    if (takeDraft?.status === "submitting" && sameProtectionPrice(activeTakePrice, takeDraft.price)) {
      dispatchTakeDraft({ type: "clear" });
    }
  }, [activeStopPrice, activeTakePrice, liveProtectionAllowed, stopDraft, takeDraft]);

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
      currentPaperState?.ok && scannerSignal !== null && activeTakePrice !== null &&
      scannerSignal.symbol === tradingSymbol
    ) {
      markSignalTakeProposalHandled(scannerSignal.signalId);
    }
  }, [activeTakePrice, currentPaperState, scannerSignal, tradingSymbol]);

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
      const authority = currentLiveAuthority();
      const normalizedPrice = normalizeLimitDraftPrice(
        draft.price, draft.authoritativeTickSize, draft.side,
      );
      if (!authority || normalizedPrice === null) {
        setLimitSubmissionFeedback("Limit confirmation unavailable: refresh the account or correct the price.");
        return;
      }
      setLimitSubmissionFeedback(null);
      const attempt = liveLimitSubmitController.current.submit(draft, {
        dispatch: dispatchLimitDraft,
        currentAuthority: currentLiveAuthority,
        createClientActionId: () =>
          globalThis.crypto?.randomUUID?.() ?? `live-limit-${Date.now()}`,
        refreshActiveLive: accountWorkspaceStore.refreshActiveLive,
      });
      return attempt.promise.then(() => undefined);
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
      const attempt = liveLimitOrderMutationController.current.cancel(
        { symbol: tradingSymbol, orderId },
        {
          currentAuthority: currentLiveAuthority,
          createClientActionId: () =>
            globalThis.crypto?.randomUUID?.() ?? `live-limit-cancel-${Date.now()}`,
          refreshActiveLive: accountWorkspaceStore.refreshActiveLive,
        },
      );
      return attempt.promise;
    }
    const attempt = paperLimitOrderMutationController.current.cancel(
      { symbol: tradingSymbol, orderId },
      {
        createClientActionId: () => `paper-limit-cancel-${Date.now()}`,
        applyPaperState: applyPaperStateForSession,
        runMutation: paperTradingStore.runMutation,
        refreshPaper: paperTradingStore.refresh,
      },
    );
    return attempt.promise;
  }, [applyPaperStateForSession, currentLiveAuthority, liveLimitAllowed, mutationsAllowed, tradingSymbol]);

  const amendPaperLimit = useCallback(async (orderId: string, price: string) => {
    if (!mutationsAllowed && !liveLimitAllowed) throw new Error("live_mutations_disabled");
    if (liveLimitAllowed) {
      const attempt = liveLimitOrderMutationController.current.amend(
        { symbol: tradingSymbol, orderId, price },
        {
          currentAuthority: currentLiveAuthority,
          createClientActionId: () =>
            globalThis.crypto?.randomUUID?.() ?? `live-limit-amend-${Date.now()}`,
          refreshActiveLive: accountWorkspaceStore.refreshActiveLive,
        },
      );
      const result = await attempt.promise;
      if (result?.status !== "accepted_pending" && result?.status !== "completed") {
        throw new Error(result?.reason_code ?? "stale_live_authority");
      }
      return;
    }
    const attempt = paperLimitOrderMutationController.current.amend(
      { symbol: tradingSymbol, orderId, price },
      {
        createClientActionId: () =>
          globalThis.crypto?.randomUUID?.() ?? `paper-limit-amend-${Date.now()}`,
        applyPaperState: applyPaperStateForSession,
        runMutation: paperTradingStore.runMutation,
        refreshPaper: paperTradingStore.refresh,
      },
    );
    await attempt.promise;
  }, [applyPaperStateForSession, currentLiveAuthority, liveLimitAllowed, mutationsAllowed, tradingSymbol]);

  const beginStopDraft = useCallback((): "drafted" | undefined => {
    if (
      (!mutationsAllowed && !liveProtectionAllowed)
      || protectionPositionSide === "Flat"
      || market.tickSize === null
    ) return;
    const referencePrice = sizingReferencePrice;
    if (activeStopPrice !== null) {
      const percent = protectionPercentFromPrice(
        "STOP",
        protectionPositionSide,
        referencePrice,
        activeStopPrice,
      );
      if (percent !== null) setStopPresetPercent(percent);
      dispatchStopDraft({
        type: "begin-edit",
        symbol: tradingSymbol,
        authoritativePrice: activeStopPrice,
      });
      return "drafted";
    }
    const price = stopPriceFromPercent(
      protectionPositionSide,
      referencePrice,
      stopPresetPercent,
      String(market.tickSize),
    );
    if (price === null) return;
    dispatchStopDraft({ type: "begin-create", symbol: tradingSymbol, price });
    return "drafted";
  }, [
    activeStopPrice,
    liveProtectionAllowed,
    market.tickSize,
    mutationsAllowed,
    protectionPositionSide,
    sizingReferencePrice,
    stopPresetPercent,
    tradingSymbol,
  ]);

  const applyStopSettings = useCallback(async (price: string, percent: string) => {
    if ((!mutationsAllowed && !liveProtectionAllowed) || protectionPositionSide === "Flat") return;
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
    dispatchStopDraft({ type: "submitting" });
    setProtectionSettings(null);

    if (liveProtectionAllowed) {
      try {
        const result = await liveProtectionMutationController.current.submit(
          {
            leg: "STOP",
            operation: activeStopPrice === null ? "CREATE" : "AMEND",
            symbol: tradingSymbol,
            triggerPrice: price,
            currentStopLoss: liveProtectionPosition?.stopLoss ?? null,
            currentTakeProfit: liveProtectionPosition?.takeProfit ?? null,
          },
          {
            currentAuthority: currentLiveProtectionAuthority,
            createClientActionId: () =>
              globalThis.crypto?.randomUUID?.() ?? `live-stop-${Date.now()}`,
            refreshActiveLive: accountWorkspaceStore.refreshActiveLive,
          },
        );
        if (
          result !== null
          && result.status !== "accepted_pending"
          && result.status !== "completed"
          && result.status !== "unknown"
          && !result.reconciliation_required
        ) {
          dispatchStopDraft({ type: "restore-editing" });
        }
      } catch {
        await accountWorkspaceStore.refreshActiveLive();
      }
      return;
    }

    try {
      const result = await paperProtectionMutationController.current.submit(
        {
          leg: "STOP",
          operation: activeStopPrice === null ? "CREATE" : "AMEND",
          symbol: tradingSymbol,
          triggerPrice: price,
        },
        {
          createClientActionId: () =>
            globalThis.crypto?.randomUUID?.() ?? `paper-stop-${Date.now()}`,
          applyPaperState: applyPaperStateForSession,
          runMutation: paperTradingStore.runMutation,
        },
      );
      if (authoritativeStopPrice(result.paper_state) !== null) {
        dispatchStopDraft({ type: "clear" });
      } else {
        dispatchStopDraft({ type: "restore-editing" });
      }
    } catch {
      dispatchStopDraft({ type: "restore-editing" });
      await paperTradingStore.refresh();
    }
  }, [
    activeStopPrice,
    currentLiveProtectionAuthority,
    liveProtectionAllowed,
    liveProtectionPosition,
    mutationsAllowed,
    protectionPositionSide,
    tradingSymbol,
  ]);

  const updateStopPreset = useCallback((percent: string) => {
    setStopPresetPercent(percent);
    saveStopPreset(percent);
    if (!stopDraft || protectionPositionSide === "Flat" || market.tickSize === null) return;
    const price = stopPriceFromPercent(
      protectionPositionSide,
      sizingReferencePrice,
      percent,
      String(market.tickSize),
    );
    if (price !== null) {
      dispatchStopDraft({ type: "update-price", price });
    }
  }, [
    market.tickSize,
    protectionPositionSide,
    sizingReferencePrice,
    stopDraft,
  ]);

  const beginTakeDraft = useCallback((): "drafted" | undefined => {
    if (
      (!mutationsAllowed && !liveProtectionAllowed)
      || protectionPositionSide === "Flat"
      || market.tickSize === null
    ) return;
    const referencePrice = sizingReferencePrice;
    if (activeTakePrice !== null) {
      const percent = protectionPercentFromPrice(
        "TAKE",
        protectionPositionSide,
        referencePrice,
        activeTakePrice,
      );
      if (percent !== null) setTakePresetPercent(percent);
      dispatchTakeDraft({
        type: "begin-edit",
        symbol: tradingSymbol,
        authoritativePrice: activeTakePrice,
      });
      return "drafted";
    }
    const price = takePriceFromPercent(
      protectionPositionSide,
      referencePrice,
      takePresetPercent,
      String(market.tickSize),
    );
    if (price === null) return;
    dispatchTakeDraft({ type: "begin-create", symbol: tradingSymbol, price });
    return "drafted";
  }, [
    activeTakePrice,
    liveProtectionAllowed,
    market.tickSize,
    mutationsAllowed,
    protectionPositionSide,
    sizingReferencePrice,
    takePresetPercent,
    tradingSymbol,
  ]);

  const applyTakeSettings = useCallback(async (price: string, percent: string) => {
    if ((!mutationsAllowed && !liveProtectionAllowed) || protectionPositionSide === "Flat") return;
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
    dispatchTakeDraft({ type: "submitting" });
    setProtectionSettings(null);

    if (liveProtectionAllowed) {
      try {
        const result = await liveProtectionMutationController.current.submit(
          {
            leg: "TAKE",
            operation: activeTakePrice === null ? "CREATE" : "AMEND",
            symbol: tradingSymbol,
            triggerPrice: price,
            currentStopLoss: liveProtectionPosition?.stopLoss ?? null,
            currentTakeProfit: liveProtectionPosition?.takeProfit ?? null,
          },
          {
            currentAuthority: currentLiveProtectionAuthority,
            createClientActionId: () =>
              globalThis.crypto?.randomUUID?.() ?? `live-take-${Date.now()}`,
            refreshActiveLive: accountWorkspaceStore.refreshActiveLive,
          },
        );
        if (
          result !== null
          && result.status !== "accepted_pending"
          && result.status !== "completed"
          && result.status !== "unknown"
          && !result.reconciliation_required
        ) {
          dispatchTakeDraft({ type: "restore-editing" });
        }
      } catch {
        await accountWorkspaceStore.refreshActiveLive();
      }
      return;
    }

    try {
      const result = await paperProtectionMutationController.current.submit(
        {
          leg: "TAKE",
          operation: activeTakePrice === null ? "CREATE" : "AMEND",
          symbol: tradingSymbol,
          triggerPrice: price,
        },
        {
          createClientActionId: () =>
            globalThis.crypto?.randomUUID?.() ?? `paper-take-${Date.now()}`,
          applyPaperState: applyPaperStateForSession,
          runMutation: paperTradingStore.runMutation,
        },
      );
      if (authoritativeTakePrice(result.paper_state) !== null) {
        if (takeDraft?.proposalSignalId) {
          markSignalTakeProposalHandled(takeDraft.proposalSignalId);
        }
        dispatchTakeDraft({ type: "clear" });
      } else {
        dispatchTakeDraft({ type: "restore-editing" });
      }
    } catch {
      dispatchTakeDraft({ type: "restore-editing" });
      await paperTradingStore.refresh();
    }
  }, [
    activeTakePrice,
    currentLiveProtectionAuthority,
    liveProtectionAllowed,
    liveProtectionPosition,
    mutationsAllowed,
    protectionPositionSide,
    takeDraft,
    tradingSymbol,
  ]);

  const updateTakePreset = useCallback((percent: string) => {
    setTakePresetPercent(percent);
    saveTakePreset(percent);
    if (!takeDraft || protectionPositionSide === "Flat" || market.tickSize === null) return;
    const price = takePriceFromPercent(
      protectionPositionSide,
      sizingReferencePrice,
      percent,
      String(market.tickSize),
    );
    if (price !== null) dispatchTakeDraft({ type: "update-price", price });
  }, [market.tickSize, protectionPositionSide, sizingReferencePrice, takeDraft]);

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
    if (!stopDraft || protectionPositionSide === "Flat" || market.tickSize === null) return;
    const closingSide = protectionPositionSide === "Long" ? "Sell" : "Buy";
    const normalized = normalizeLimitDraftPrice(
      rawPrice, String(market.tickSize), closingSide,
    );
    if (normalized !== null) {
      dispatchStopDraft({ type: "update-price", price: normalized });
      const percent = protectionPercentFromPrice(
        "STOP",
        protectionPositionSide,
        sizingReferencePrice,
        normalized,
      );
      if (percent !== null) setStopPresetPercent(percent);
    }
  }, [
    market.tickSize,
    protectionPositionSide,
    sizingReferencePrice,
    stopDraft,
  ]);

  const updateTakeDraftPrice = useCallback((rawPrice: string) => {
    if (!takeDraft || protectionPositionSide === "Flat" || market.tickSize === null) return;
    const closingSide = protectionPositionSide === "Long" ? "Sell" : "Buy";
    const normalized = normalizeLimitDraftPrice(rawPrice, String(market.tickSize), closingSide);
    if (normalized !== null) {
      dispatchTakeDraft({ type: "update-price", price: normalized });
      const percent = protectionPercentFromPrice(
        "TAKE",
        protectionPositionSide,
        sizingReferencePrice,
        normalized,
      );
      if (percent !== null) setTakePresetPercent(percent);
    }
  }, [market.tickSize, protectionPositionSide, sizingReferencePrice, takeDraft]);

  const confirmProtectionDraft = useCallback(async (leg: "STOP" | "TAKE") => {
    const draft = leg === "STOP" ? stopDraft : takeDraft;
    const dispatch = leg === "STOP" ? dispatchStopDraft : dispatchTakeDraft;
    if (
      !draft
      || draft.status === "submitting"
      || (!mutationsAllowed && !liveProtectionAllowed)
    ) return;
    dispatch({ type: "submitting" });
    if (liveProtectionAllowed) {
      try {
        const result = await liveProtectionMutationController.current.submit(
          {
            leg,
            operation: draft.mode === "CREATE" ? "CREATE" : "AMEND",
            symbol: tradingSymbol,
            triggerPrice: draft.price,
            currentStopLoss: liveProtectionPosition?.stopLoss ?? null,
            currentTakeProfit: liveProtectionPosition?.takeProfit ?? null,
          },
          {
            currentAuthority: currentLiveProtectionAuthority,
            createClientActionId: () =>
              globalThis.crypto?.randomUUID?.() ?? `live-${leg.toLowerCase()}-${Date.now()}`,
            refreshActiveLive: accountWorkspaceStore.refreshActiveLive,
          },
        );
        if (
          result !== null
          && result.status !== "accepted_pending"
          && result.status !== "completed"
          && result.status !== "unknown"
          && !result.reconciliation_required
        ) {
          dispatch({ type: "restore-editing" });
        }
      } catch {
        await accountWorkspaceStore.refreshActiveLive();
      }
      return;
    }
    try {
      const result = await paperProtectionMutationController.current.submit(
        {
          leg,
          operation: draft.mode === "CREATE" ? "CREATE" : "AMEND",
          symbol: tradingSymbol,
          triggerPrice: draft.price,
        },
        {
          createClientActionId: () =>
            globalThis.crypto?.randomUUID?.() ?? `paper-${leg.toLowerCase()}-${Date.now()}`,
          applyPaperState: applyPaperStateForSession,
          runMutation: paperTradingStore.runMutation,
        },
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
  }, [
    currentLiveProtectionAuthority,
    liveProtectionAllowed,
    liveProtectionPosition,
    mutationsAllowed,
    stopDraft,
    takeDraft,
    tradingSymbol,
  ]);

  const deleteProtection = useCallback(async (leg: "STOP" | "TAKE") => {
    if ((leg === "STOP" ? activeStopPrice : activeTakePrice) === null) return;
    if (!mutationsAllowed && !liveProtectionAllowed) return;
    if (liveProtectionAllowed) {
      try {
        await liveProtectionMutationController.current.submit(
          {
            leg,
            operation: "DELETE",
            symbol: tradingSymbol,
            currentStopLoss: liveProtectionPosition?.stopLoss ?? null,
            currentTakeProfit: liveProtectionPosition?.takeProfit ?? null,
          },
          {
            currentAuthority: currentLiveProtectionAuthority,
            createClientActionId: () =>
              globalThis.crypto?.randomUUID?.() ?? `live-${leg.toLowerCase()}-delete-${Date.now()}`,
            refreshActiveLive: accountWorkspaceStore.refreshActiveLive,
          },
        );
      } catch {
        await accountWorkspaceStore.refreshActiveLive();
      }
      return;
    }
    try {
      await paperProtectionMutationController.current.submit(
        {
          leg,
          operation: "DELETE",
          symbol: tradingSymbol,
        },
        {
          createClientActionId: () =>
            globalThis.crypto?.randomUUID?.() ?? `paper-${leg.toLowerCase()}-delete-${Date.now()}`,
          applyPaperState: applyPaperStateForSession,
          runMutation: paperTradingStore.runMutation,
        },
      );
    } catch {
      await paperTradingStore.refresh();
    }
  }, [
    activeStopPrice,
    activeTakePrice,
    currentLiveProtectionAuthority,
    liveProtectionAllowed,
    liveProtectionPosition,
    mutationsAllowed,
    tradingSymbol,
  ]);

  const visibleLimitDrafts =
    limitDraftState.drafts ??
    (limitDraftState.draft ? [limitDraftState.draft] : []);

  return (
    <main className={`workspace-shell${mode === "EDITOR" ? " workspace-editor" : ""}`}>
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
      {mode === "EDITOR" && launchLink?.mode === "EDITOR" && !launchLink.signalId && (
        <output role="status" aria-live="polite">
          Исходный сигнал не указан в ссылке. Показаны текущие свечи без сохранённых линий паттерна.
        </output>
      )}
      {(mode === "TERMINAL" || mode === "AUTOPILOT") && launchLink?.mode === "TERMINAL" && launchLink.signalId
        && tradingSymbol === launchLink.symbol && timeframe === launchLink.timeframe && (
          <output role="status" aria-live="polite">
            {terminalSignalDrawings
              ? `Исходная геометрия сигнала: ${frozenSignal?.originalPattern ?? launchLink.signalId}`
              : frozenGeometryStatus === "loading"
                ? "Загрузка исходной геометрии сигнала…"
                : "Линии исходного сигнала недоступны на текущих свечах; ордера не изменены."}
          </output>
        )}
      <section className="workspace-grid" aria-label="Trading workspace">
        <div
          className={`workspace-market-row ${mode !== "EDITOR" && marketSidePanelOpen ? "side-panel-open" : "side-panel-closed"}`}
        >
          {mode === "EDITOR" && launchLink?.signalId && !frozenSignal ? (
            <div role="status" aria-live="polite">
              {frozenGeometryStatus === "loading"
                ? "Загрузка сохранённых линий исходного сигнала…"
                : "Исходная геометрия недоступна. Текущие свечи не заменяют исходный сигнал."}
            </div>
          ) : (
          <ChartPanel
          key={mode === "EDITOR" && frozenSignal ? `frozen:${frozenSignal.signalId}:${frozenSignal.savedReviewId ?? "initial"}` : `${market.book.symbol}:${timeframe}:${mode}`}
          candles={mode === "EDITOR" && frozenSignal ? frozenSignal.candles : market.candles}
          editorMode={mode === "EDITOR"}
          onEditorNavigate={setMode}
          retrospectiveContext={mode === "EDITOR" ? frozenSignal?.context ?? null : null}
          onExtendEditorHistory={mode === "EDITOR" && frozenSignal ? async () => {
            const current = frozenSignal;
            const response = await fetch(
              `/api/workspace/signal-geometry/continuation?signal_id=${encodeURIComponent(current.signalId)}`,
              { credentials: "same-origin" },
            );
            const data = await response.json();
            if (!response.ok || data.ok !== true ||
                data.signal_id !== current.signalId ||
                data.source_revision !== current.snapshotRevision ||
                !Array.isArray(data.bars) ||
                typeof data.bars_sha256 !== "string" ||
                !/^[0-9a-f]{64}$/i.test(data.bars_sha256))
              throw new Error(data.error || "Нет подтверждённых последующих свечей");
            const expanded = appendRetrospectiveCandles(
              current.sourceCandles, data.bars as RetrospectiveOhlc[],
              launchLink?.timeframe ?? timeframe, data.as_of_ms,
            );
            // Existing owner edits use stable logical indices: refuse a
            // changed historical prefix, never silently shift those anchors.
            if (expanded.length < current.candles.length ||
                expanded.slice(0, current.candles.length).some(
                  (bar, index) => JSON.stringify(bar) !== JSON.stringify(current.candles[index]),
                ))
              throw new Error("История свечей изменилась; текущая разметка сохранена");
            if (expanded.length === current.candles.length)
              throw new Error("Новых закрытых свечей пока нет");
            setFrozenSignal((previous) =>
              previous?.signalId === current.signalId &&
              previous.snapshotRevision === current.snapshotRevision
                ? { ...previous, candles: expanded, context: {
                    asOfMs: data.as_of_ms, barsSha256: data.bars_sha256,
                  } }
                : previous,
            );
          } : undefined}
          referenceDrawings={mode === "EDITOR"
            ? frozenSignal?.referenceDrawings ?? []
            : mode === "TERMINAL" || mode === "AUTOPILOT" ? terminalSignalDrawings ?? [] : []}
          editableSeedDrawings={mode === "EDITOR" ? frozenSignal?.editableDrawings ?? [] : []}
          signalIdentity={mode === "EDITOR" ? frozenSignal?.signalId ?? null : null}
          originalPattern={mode === "EDITOR" ? frozenSignal?.originalPattern ?? null : null}
          snapshotRevision={mode === "EDITOR" ? frozenSignal?.snapshotRevision ?? null : null}
          barsSha256={mode === "EDITOR" ? frozenSignal?.barsSha256 ?? null : null}
          savedReviewId={mode === "EDITOR" ? frozenSignal?.savedReviewId ?? null : null}
          savedReviewLabel={mode === "EDITOR" ? frozenSignal?.savedReviewLabel ?? null : null}
          savedReviewNote={mode === "EDITOR" ? frozenSignal?.savedReviewNote ?? null : null}
          onSubmitOwnerSignal={mode === "EDITOR" && frozenSignal ? async (
            proposal: OwnerSignalDraft,
          ) => {
            if (proposal.signal_id !== frozenSignal.signalId ||
                proposal.snapshot_revision !== frozenSignal.snapshotRevision ||
                proposal.bars_sha256 !== frozenSignal.barsSha256)
              throw new Error("Исходный сигнал изменился");
            const response = await fetch("/api/workspace/owner-signal-proposal", {
              method: "POST", credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(proposal),
            });
            const result = await response.json();
            const record = result.proposal;
            if (!response.ok || result.ok !== true ||
                typeof record?.proposal_id !== "string" ||
                !/^[0-9a-f]{64}$/.test(record.proposal_id) ||
                record?.submission?.signal_id !== proposal.signal_id ||
                record?.submission?.snapshot_revision !== proposal.snapshot_revision ||
                record?.submission?.bars_sha256 !== proposal.bars_sha256 ||
                record?.submission?.pattern !== proposal.pattern ||
                record?.submission?.idempotency_key !== proposal.idempotency_key ||
                record?.submission?.context_as_of_ms !== proposal.context_as_of_ms ||
                record?.submission?.context_bars_sha256 !== proposal.context_bars_sha256 ||
                record?.candidate_created !== false || record?.robot_candidate_id !== null ||
                typeof record?.assessment?.decision !== "string" ||
                typeof record?.assessment?.reason !== "string")
              throw new Error(result.error || "Нет подтверждённой оценки новой разметки");
            return {
              proposalId: record.proposal_id,
              decision: record.assessment.decision,
              reason: record.assessment.reason,
            };
          } : undefined}
          onSaveGeometryReview={mode === "EDITOR" && frozenSignal ? async (
            review: GeometryReviewDraft & { note: string; idempotency_key: string },
          ) => {
            if (review.signal_id !== frozenSignal.signalId
                || review.snapshot_revision !== frozenSignal.snapshotRevision
                || review.bars_sha256 !== frozenSignal.barsSha256)
              throw new Error("Несовпадение исходного сигнала");
            const verifiedReceipt = (record: { review_id?: unknown; submission?: unknown } | null | undefined) =>
              typeof record?.review_id === "string"
              && /^[0-9a-f]{64}$/.test(record.review_id)
              && matchesStoredGeometryReview(review, record.submission)
                ? { reviewId: record.review_id as string, label: review.label }
                : null;
            let failure: string | null = null;
            try {
              const response = await fetch("/api/workspace/geometry-feedback", {
                method: "POST", credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(review),
              });
              const result = await response.json();
              if (response.ok && result.ok === true) {
                const receipt = verifiedReceipt(result.review);
                if (receipt) return receipt;
              }
              failure = result.error || "Сервер не подтвердил точное сохранение отзыва";
              // Definitive client errors are not transport ambiguity.
              if (response.status >= 400 && response.status < 500)
                throw new Error(failure ?? "Сервер отклонил сохранение");
            } catch (error) {
              failure = error instanceof Error ? error.message : "Нет ответа сервера";
              if (failure && failure !== "Failed to fetch" && failure !== "NetworkError when attempting to fetch resource."
                  && failure !== "Сервер не подтвердил точное сохранение отзыва"
                  && !/^(geometry_feedback_unavailable|Unexpected token|JSON)/.test(failure))
                throw error;
            }
            // A POST can commit durably before the browser loses its response.
            // Confirm exact identity and idempotency key; never infer success from HTTP alone.
            try {
              const response = await fetch(
                `/api/workspace/signal-geometry?signal_id=${encodeURIComponent(review.signal_id)}`,
                { credentials: "same-origin" },
              );
              if (response.ok) {
                const result = await response.json();
                const receipt = result.ok === true ? verifiedReceipt(result.latest_review) : null;
                if (receipt) return receipt;
              }
            } catch {
              // Unknown outcome must remain explicitly unconfirmed.
            }
            throw new Error(`${failure ?? "Нет подтверждения"}; запись не подтверждена, повторите сохранение`);
          } : undefined}
          tickSize={mode === "EDITOR" && frozenSignal ? null : market.tickSize}
          symbol={mode === "EDITOR" && frozenSignal ? launchLink?.symbol ?? market.book.symbol : market.book.symbol}
          timeframe={mode === "EDITOR" && frozenSignal ? launchLink?.timeframe ?? timeframe : timeframe}
          activeLimitOrders={
            mode === "TERMINAL" && currentPaperState?.ok ? currentPaperState.active_limit_orders :
            mode === "AUTOPILOT" && robotPosition && currentPaperState?.ok ? currentPaperState.active_limit_orders : []
          }
          pendingLimitDraft={mode !== "TERMINAL" ? null : limitDraftState.draft}
          liveLimitDrafts={accountProjection?.provider === "BYBIT"}
          pendingLimitDrafts={mode !== "TERMINAL" ? [] : visibleLimitDrafts}
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
          fastLimitActive={mode === "TERMINAL" && fastLimitIntent !== null}
          onFastLimitPriceSelect={createFastLimitDraft}
          onActiveLimitAmend={mode === "TERMINAL" ? amendPaperLimit : undefined}
          onActiveLimitCancel={mode === "TERMINAL" ? cancelPaperLimit : undefined}
          authoritativeStopPrice={mode === "TERMINAL" || (mode === "AUTOPILOT" && robotPosition) ? activeStopPrice : null}
          stopDraft={mode !== "TERMINAL" ? null : stopDraft}
          onStopDraftPriceChange={updateStopDraftPrice}
          onStopConfirm={() => {
            setProtectionSettings(null);
            return confirmProtectionDraft("STOP");
          }}
          onStopCancelDraft={() => {
            setProtectionSettings(null);
            dispatchStopDraft({ type: "clear" });
          }}
          onStopEdit={beginStopEdit}
          onStopDelete={() => deleteProtection("STOP")}
          authoritativeTakePrice={mode === "TERMINAL" || (mode === "AUTOPILOT" && robotPosition) ? activeTakePrice : null}
          takeDraft={mode !== "TERMINAL" ? null : takeDraft}
          onTakeDraftPriceChange={updateTakeDraftPrice}
          onTakeConfirm={() => {
            setProtectionSettings(null);
            return confirmProtectionDraft("TAKE");
          }}
          onTakeCancelDraft={() => {
            setProtectionSettings(null);
            dismissTakeDraft();
          }}
          onTakeEdit={beginTakeEdit}
          onTakeDelete={() => deleteProtection("TAKE")}
          averageEntryPrice={mode === "TERMINAL" && protectionPositionSide !== "Flat" || mode === "AUTOPILOT" && robotPosition ? protectionAverageEntry : null}
          readOnly={mode === "AUTOPILOT"}
          robotTradeMarkers={mode === "AUTOPILOT" && robotPosition &&
            robotMarkers?.symbol === tradingSymbol &&
            robotMarkers.tradeId === robotPosition.robot_trade_id
              ? robotMarkers.markers : []}
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
          )}
          {mode !== "EDITOR" && (
            <>
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
                    positionSide={mode === "AUTOPILOT" ? robotPosition?.position_side ?? "Flat" : positionSide}
                    averageEntryPrice={mode === "AUTOPILOT" ? (robotPosition?.average_entry === null || !robotPosition ? null : Number(robotPosition.average_entry)) : positionAverageEntry}
                    currentPrice={liveMidPrice}
                    compression={domCompression}
                    viewportGeometry={domViewportGeometry}
                  />
                  <DomPanel
                    book={market.book}
                    centerPrice={ladderCenterPrice}
                    onCenterPriceChange={setLadderCenterPrice}
                    ownOrders={mode === "AUTOPILOT" && !robotPosition ? [] : domOwnOrders}
                    ownOrdersReadOnly={mode === "AUTOPILOT"}
                    positionSummary={mode === "AUTOPILOT" ? robotPosition : null}
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
            </>
          )}
        </div>
        <ModePanel
          mode={mode}
          onModeChange={setMode}
          onRobotPositionsLoaded={setRobotPositions}
          verifiedRobotPosition={robotPosition}
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
          protectionPositionSide={protectionPositionSide}
          onStopTap={() => {
            const result = beginStopDraft();
            setProtectionSettings({ leg: "STOP", symbol: tradingSymbol });
            return result;
          }}
          onStopHold={() => {
            beginStopDraft();
            setProtectionSettings({ leg: "STOP", symbol: tradingSymbol });
          }}
          stopActive={activeStopPrice !== null}
          stopSettingsOpen={protectionSettings?.leg === "STOP" && protectionSettings.symbol === tradingSymbol}
          stopPresetPercent={stopPresetPercent}
          stopReferencePrice={sizingReferencePrice}
          onStopSettingsApply={applyStopSettings}
          onStopPresetChange={updateStopPreset}
          onStopSettingsClose={() => {
            setProtectionSettings(null);
            dispatchStopDraft({ type: "clear" });
          }}
          onTakeTap={() => {
            const result = beginTakeDraft();
            setProtectionSettings({ leg: "TAKE", symbol: tradingSymbol });
            return result;
          }}
          onTakeHold={() => {
            beginTakeDraft();
            setProtectionSettings({ leg: "TAKE", symbol: tradingSymbol });
          }}
          takeActive={activeTakePrice !== null}
          takeSettingsOpen={protectionSettings?.leg === "TAKE" && protectionSettings.symbol === tradingSymbol}
          takePresetPercent={takePresetPercent}
          takeReferencePrice={sizingReferencePrice}
          onTakeSettingsApply={applyTakeSettings}
          onTakePresetChange={updateTakePreset}
          onTakeSettingsClose={() => {
            setProtectionSettings(null);
            dismissTakeDraft();
          }}
          onWorkspaceSymbolSelect={switchWorkspaceSymbol}
          accountOpen={accountOpen}
          onAccountToggle={() => setAccountOpen((open) => !open)}
          accountWorkspaceProjection={accountProjection}
          mutationsAllowed={mutationsAllowed}
          liveMarketAllowed={liveMarketAllowed}
          liveLimitAllowed={liveLimitAllowed}
          liveProtectionAllowed={liveProtectionAllowed}
        />
      </section>
    </main>
  );
}
