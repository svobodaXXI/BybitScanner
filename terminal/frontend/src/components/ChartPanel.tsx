import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  LineStyle,
  type LogicalRange,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type DrawingCoordinates,
  DrawingOverlay,
} from "../chart/DrawingOverlay";
import { DrawingToolbar } from "../chart/DrawingToolbar";
import { DrawingClearConfirmation } from "../chart/DrawingClearConfirmation";
import {
  DrawingHistory,
  clearDrawingHistory,
  type DrawingObject,
  type DrawingTool,
  deserializeDrawings,
  serializeDrawings,
} from "../chart/drawingModel";
import { chartAxisTarget } from "../chart/axisHitTest";
import {
  activateTouchCrosshair,
  CROSSHAIR_HOLD_MS,
  moveTouchCrosshair,
  releaseTouchCrosshair,
  type TouchCrosshairState,
} from "../chart/crosshairInteraction";
import {
  DEFAULT_RIGHT_OFFSET_BARS,
  replaceSeriesDataPreservingViewport,
} from "../chart/followLatest";
import {
  calculateDirectionalPinch,
  scaleRangeAroundAnchor,
  translateLogicalRangeByPixels,
  translatePriceRangeByPixels,
} from "../chart/gestureMath";
import { chartPriceFormat } from "../chart/priceFormat";
import { editorMoscowCrosshairTime, editorMoscowTickMark } from "../chart/editorMoscowTime";
import { candleCloseStatus } from "../chart/candleCloseStatus";
import { createFrameBatcher } from "../chart/frameBatcher";
import type { Candle } from "../contracts/marketData";
import {
  TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR,
  visibleRobotTradeMarkers, type RobotTradeMarker,
} from "../chart/robotTradeMarkers";
import { buildEditorGeometryReview, isValidCachedEditorDraft, type GeometryReviewDraft } from "../geometryFeedback/geometryReviewDraft";
import { initialSourceGeometryRange } from "../geometryFeedback/signalChartBridge";
import { buildOwnerChartDraftV3, buildOwnerSignalDraft, type OwnerChartDraftV3, type OwnerChartPatternV3, type OwnerChartMovement, type OwnerWedgeSubtype, type OwnerSignalDraft } from "../geometryFeedback/ownerSignalDraft";
import type { MarketSide, PaperLimitOrder } from "../contracts/trading";
import type { LimitDraft } from "../orders/limitDraft";
import { normalizedLimitDraftPrice } from "../orders/limitDraft";
import { PendingLimitLine } from "../chart/PendingLimitLine";
import { StopLine } from "../chart/StopLine";
import type { StopDraft } from "../orders/stopDraft";
import {
  cancelVisibleLimitCandidates,
  confirmVisibleLimitCandidates,
  useActiveLimitEdit,
} from "../chart/activeLimitEdit";
import { TradingControlButton } from "../interactions/useTradingControlActivation";
import { normalizeLimitDraftPrice } from "../orders/limitDraft";

const PRICE_SCALE_WIDTH_FALLBACK = 64,
  TIME_SCALE_HEIGHT = 30,
  BASE_TIME = 1_700_000_000;
const candleTime = (c: Candle, i: number): UTCTimestamp => {
  const parsed = Date.parse(c.time);
  return (
    Number.isFinite(parsed) ? Math.floor(parsed / 1000) : BASE_TIME + i * 300
  ) as UTCTimestamp;
};
type Series = ISeriesApi<"Candlestick", Time>;
type Gesture =
  | {
      type: "pinch";
      ids: [number, number];
      dx: number;
      dy: number;
      logical: number;
      price: number;
      xRange: LogicalRange;
      priceRange: { from: number; to: number };
    }
  | {
      type: "axis-y" | "axis-x";
      id: number;
      startX: number;
      startY: number;
      xRange: LogicalRange;
      priceRange: { from: number; to: number };
    }
  | {
      type: "plot-pan";
      id: number;
      startX: number;
      startY: number;
      xRange: LogicalRange;
      priceRange: { from: number; to: number };
    }
  | null;

export function ChartPanel({
  candles,
  tickSize,
  symbol = "BTCUSDT",
  timeframe = "5m",
  activeLimitOrders = [],
  pendingLimitDraft = null,
  pendingLimitDrafts,
  liveLimitDrafts = false,
  pendingLimitVolumeValid = { Buy: true, Sell: true },
  onPendingLimitSelect,
  onPendingLimitDismiss,
  onPendingLimitDismissAll,
  onPendingLimitPriceChange,
  onPendingLimitConfirm,
  fastLimitActive = false,
  onFastLimitPriceSelect,
  onActiveLimitAmend,
  onActiveLimitCancel,
  authoritativeStopPrice = null,
  stopDraft = null,
  onStopDraftPriceChange,
  onStopConfirm,
  onStopCancelDraft,
  onStopEdit,
  onStopDelete,
  authoritativeTakePrice = null,
  takeDraft = null,
  onTakeDraftPriceChange,
  onTakeConfirm,
  onTakeCancelDraft,
  onTakeEdit,
  onTakeDelete,
  averageEntryPrice = null,
  workspaceControls,
  positionFooter,
  readOnly = false,
  robotTradeMarkers = [],
  editorMode = false,
  referenceDrawings = [],
  editableSeedDrawings = [],
  signalIdentity = null,
  originalPattern = null,
  snapshotRevision = null,
  barsSha256 = null,
  savedReviewId = null,
  savedReviewLabel = null,
  savedReviewNote = null,
  onSaveGeometryReview,
  onSubmitOwnerSignal,
  retrospectiveContext = null,
  onExtendEditorHistory,
  onEditorNavigate,
  onShowCurrentEditorChart,
  ownerChartMode = false,
  onSubmitOwnerChart,
}: {
  candles: readonly Candle[];
  tickSize: number | null;
  symbol?: string;
  timeframe?: string;
  activeLimitOrders?: readonly PaperLimitOrder[];
  pendingLimitDraft?: LimitDraft | null;
  pendingLimitDrafts?: readonly LimitDraft[];
  liveLimitDrafts?: boolean;
  pendingLimitVolumeValid?: Readonly<Record<MarketSide, boolean>>;
  onPendingLimitSelect?: (draftId: string) => void;
  onPendingLimitDismiss?: (draftId: string) => void;
  onPendingLimitDismissAll?: () => void;
  onPendingLimitPriceChange?: (price: string, draftId?: string) => void;
  onPendingLimitConfirm?: (draftId?: string) => void | Promise<void>;
  fastLimitActive?: boolean;
  onFastLimitPriceSelect?: (price: string) => void;
  onActiveLimitAmend?: (orderId: string, price: string) => Promise<void>;
  onActiveLimitCancel?: (orderId: string) => Promise<unknown>;
  authoritativeStopPrice?: string | null;
  stopDraft?: StopDraft | null;
  onStopDraftPriceChange?: (price: string) => void;
  onStopConfirm?: () => void | Promise<void>;
  onStopCancelDraft?: () => void;
  onStopEdit?: () => void;
  onStopDelete?: () => void | Promise<void>;
  authoritativeTakePrice?: string | null;
  takeDraft?: StopDraft | null;
  onTakeDraftPriceChange?: (price: string) => void;
  onTakeConfirm?: () => void | Promise<void>;
  onTakeCancelDraft?: () => void;
  onTakeEdit?: () => void;
  onTakeDelete?: () => void | Promise<void>;
  averageEntryPrice?: string | null;
  workspaceControls?: ReactNode;
  positionFooter?: ReactNode;
  /** Robot observation: no active order or protection interactions. */
  readOnly?: boolean;
  /** Confirmed Telegram card TradeMarkers. Never projected for manual/Editor. */
  robotTradeMarkers?: readonly RobotTradeMarker[];
  editorMode?: boolean;
  /** Read-only source geometry; only supplied from a verified signal snapshot. */
  referenceDrawings?: readonly DrawingObject[];
  editableSeedDrawings?: readonly DrawingObject[];
  signalIdentity?: string | null;
  originalPattern?: string | null;
  snapshotRevision?: string | null;
  barsSha256?: string | null;
  savedReviewId?: string | null;
  savedReviewLabel?: GeometryReviewDraft["label"] | null;
  savedReviewNote?: string | null;
  onSaveGeometryReview?: (review: GeometryReviewDraft & { note: string; idempotency_key: string }) =>
    Promise<{ reviewId: string; label: GeometryReviewDraft["label"] }>;
  onSubmitOwnerSignal?: (proposal: OwnerSignalDraft) => Promise<{ proposalId: string; decision: string; reason: string }>;
  retrospectiveContext?: { asOfMs: number; barsSha256: string } | null;
  onExtendEditorHistory?: () => Promise<void>;
  onEditorNavigate?: (mode: "TERMINAL" | "AUTOPILOT") => void;
  onShowCurrentEditorChart?: () => void;
  ownerChartMode?: boolean;
  onSubmitOwnerChart?: (proposal: OwnerChartDraftV3) => Promise<{ proposalId: string; decision: string; reason: string }>;
}) {
  const [candleClockMs, setCandleClockMs] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setCandleClockMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const hostRef = useRef<HTMLDivElement>(null),
    chartRef = useRef<IChartApi | null>(null),
    seriesRef = useRef<Series | null>(null);
  const averageEntryLineRef = useRef<IPriceLine | null>(null);
  const averageEntryLineSymbolRef = useRef<string | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>()),
    gesture = useRef<Gesture>(null);
  const touchCrosshair = useRef<{
    state: TouchCrosshairState;
    pointerId: number | null;
    last: { x: number; y: number } | null;
    timer: ReturnType<typeof setTimeout> | null;
  }>({ state: { mode: "IDLE" }, pointerId: null, last: null, timer: null });
  const followLatestRef = useRef(true);
  const initialSourceFrameApplied = useRef(false);
  const previousEditorBars = useRef<number | null>(null);
  const panBatcherRef = useRef<ReturnType<typeof createFrameBatcher> | null>(null);
  const [renderTick, setRenderTick] = useState(0),
    [tool, setTool] = useState<DrawingTool>(ownerChartMode ? "crosshair" : "select"),
    [magnet, setMagnet] = useState(editorMode),
    [selectedId, setSelectedId] = useState<string | null>(null),
    [clearConfirmationOpen, setClearConfirmationOpen] = useState(false),
    [confirmAllPendingOpen, setConfirmAllPendingOpen] = useState(false),
    [dismissAllPendingOpen, setDismissAllPendingOpen] = useState(false);
  const [newSignalMode, setNewSignalMode] = useState(ownerChartMode);
  const storageKey = `bybitscanner:${newSignalMode ? "new-signal-drawings" : editorMode ? "editor-drawings" : "drawings"}:v1:${symbol}:${timeframe}${editorMode && signalIdentity ? `:${signalIdentity}${savedReviewId && !newSignalMode ? `:review-${savedReviewId}` : ""}` : ""}${editorMode && retrospectiveContext ? `:review-asof-${retrospectiveContext.asOfMs}` : ""}`;
  const historyRef = useRef(
    new DrawingHistory(
      (() => {
        // For a server-confirmed review, the verified frozen source and
        // reviewed rays are authoritative. Local drafts from an earlier session
        // must never override those immutable UTC anchors.
        // Unsaved initial Editor work and ordinary trading drawings retain
        // their existing local draft recovery behavior.
        if (!(editorMode && signalIdentity && savedReviewId)) {
          // Browser storage can throw SecurityError or QuotaExceededError
          // (private mode, managed devices, storage disabled). Optional local
          // drafts cannot prevent an authenticated frozen Editor opening.
          try {
            const stored = globalThis.localStorage?.getItem(storageKey);
            if (stored !== null && stored !== undefined) {
              const recovered = deserializeDrawings(stored);
              // Only Editor requires exact original topology and valid frozen
              // anchors; preserve regular trading drawing recovery as before.
              if (!editorMode || !signalIdentity ||
                  isValidCachedEditorDraft(recovered, referenceDrawings, candles))
                return recovered;
            }
          } catch {
            // Fall back to immutable Scanner/review seed; never refit live bars.
          }
        }
        return editableSeedDrawings.map((drawing) => ({
          ...drawing,
          anchors: drawing.anchors.map((anchor) => ({ ...anchor })),
          style: { ...drawing.style },
        }));
      })(),
    ),
  );
  const correctionHistoryRef = useRef(historyRef.current);
  const proposalHistoryRef = useRef(new DrawingHistory([]));
  const [drawings, setDrawings] = useState<DrawingObject[]>(historyRef.current.current);
  const [proposalPattern, setProposalPattern] = useState<OwnerChartPatternV3 | "">(ownerChartMode ? "" : "Wedge");
  const [proposalDirection, setProposalDirection] = useState<OwnerChartMovement | "">("");
  const [proposalWedgeSubtype, setProposalWedgeSubtype] = useState<OwnerWedgeSubtype | "">("");
  const [proposalNote, setProposalNote] = useState("");
  const [proposalPending, setProposalPending] = useState(false);
  const [proposalStatus, setProposalStatus] = useState("");
  const [extensionPending, setExtensionPending] = useState(false);
  const [, setExtensionStatus] = useState("");
  const proposalToken = useRef<{ content: string; key: string } | null>(null);
  const [reviewLabel, setReviewLabel] = useState<GeometryReviewDraft["label"]>(
    savedReviewLabel ?? "GEOMETRY_CORRECTED",
  );
  // Persisted review text belongs to the same immutable review ID as the
  // restored editable rays. A fresh editor must not silently erase the note.
  const [reviewNote, setReviewNote] = useState(savedReviewNote ?? "");
  const [reviewPending, setReviewPending] = useState(false);
  const [reviewStatus, setReviewStatus] = useState("");
  const reviewEditSequence = useRef(0);
  const [reviewDirty, setReviewDirty] = useState(() =>
    Boolean(editorMode && signalIdentity && (
      drawings.length !== editableSeedDrawings.length ||
      drawings.some((drawing) => {
        const source = editableSeedDrawings.find((seed) => seed.id === drawing.id);
        return !source || JSON.stringify(drawing.anchors) !== JSON.stringify(source.anchors);
      })
    )),
  );
  const markReviewEdited = useCallback(() => {
    if (!editorMode || !signalIdentity) return;
    reviewEditSequence.current += 1;
    setReviewDirty(true);
    setReviewStatus("");
  }, [editorMode, signalIdentity]);
  const previousReviewAsOf = useRef(retrospectiveContext?.asOfMs ?? null);
  useEffect(() => {
    const current = retrospectiveContext?.asOfMs ?? null;
    const previous = previousReviewAsOf.current;
    previousReviewAsOf.current = current;
    if (previous !== current && current !== null && !newSignalMode) markReviewEdited();
  }, [retrospectiveContext?.asOfMs, newSignalMode, markReviewEdited]);
  const submitToken = useRef<{ content: string; key: string } | null>(null);
  const saveCorrection = async () => {
    if (newSignalMode) return;
    if (!editorMode || !signalIdentity || !snapshotRevision || !barsSha256 || !onSaveGeometryReview || reviewPending) return;
    try {
      const draft = buildEditorGeometryReview({
        signalId: signalIdentity, snapshotRevision, barsSha256,
        label: reviewLabel, frozenCandles: candles,
        referenceDrawings, editableDrawings: drawings,
        contextAsOfMs: retrospectiveContext?.asOfMs,
        contextBarsSha256: retrospectiveContext?.barsSha256,
      });
      const note = reviewNote.trim();
      const content = JSON.stringify({ ...draft, note });
      if (submitToken.current?.content !== content) {
        const key = globalThis.crypto?.randomUUID?.() ?? `geometry-review-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        submitToken.current = { content, key };
      }
      const submittedSequence = reviewEditSequence.current;
      setReviewPending(true);
      setReviewStatus("Сохранение исправления…");
      await onSaveGeometryReview({
        ...draft, note, idempotency_key: submitToken.current.key,
      });
      if (submittedSequence === reviewEditSequence.current) {
        setReviewDirty(false);
        setReviewStatus(reviewLabel === "GEOMETRY_CORRECTED" ? "Исправлена геометрия" : "");
      } else {
        setReviewDirty(true);
        setReviewStatus("");
      }
    } catch (error) {
      setReviewStatus(`Не удалось сохранить: ${error instanceof Error ? error.message : "неизвестная ошибка"}`);
    } finally {
      setReviewPending(false);
    }
  };
  const commit = useCallback((next: DrawingObject[]) => {
    historyRef.current.commit(next);
    setDrawings(next);
    if (!newSignalMode) markReviewEdited();
    else setProposalStatus("");
  }, [newSignalMode, markReviewEdited]);

  const switchSignalDrawingMode = () => {
    if (reviewPending || proposalPending) return;
    if (newSignalMode) {
      proposalHistoryRef.current = historyRef.current;
      historyRef.current = correctionHistoryRef.current;
      setDrawings(historyRef.current.current);
      setNewSignalMode(false);
      setTool("select");
    } else {
      correctionHistoryRef.current = historyRef.current;
      // Restore the owner's separate new-signal draft only from this exact
      // source signal, never from the original Scanner correction cache.
      if (proposalHistoryRef.current.current.length === 0) {
        try {
          const key = `bybitscanner:new-signal-drawings:v1:${symbol}:${timeframe}:${signalIdentity}`;
          const cached = deserializeDrawings(globalThis.localStorage?.getItem(key) ?? null);
          if (cached.length <= 2 && cached.every((line) =>
            line.type === "ray" && line.anchors.length === 2 &&
            !line.hidden && typeof line.id === "string" &&
            line.anchors.every((anchor) =>
              Number.isInteger(anchor.logical) && anchor.logical >= 0 &&
              anchor.logical < candles.length &&
              Number.isFinite(anchor.price) && anchor.price > 0) &&
            typeof line.style?.color === "string" && Number.isFinite(line.style?.lineWidth)
          )) proposalHistoryRef.current = new DrawingHistory(cached);
        } catch {
          // Optional browser cache must never prevent opening the Editor.
        }
      }
      historyRef.current = proposalHistoryRef.current;
      setDrawings(historyRef.current.current);
      setNewSignalMode(true);
      setTool("crosshair");
    }
    setSelectedId(null);
    setClearConfirmationOpen(false);
  };
  const submitOwnerProposal = async () => {
    if (!newSignalMode || proposalPending || reviewPending ||
        (ownerChartMode ? !onSubmitOwnerChart || !proposalPattern || !proposalDirection || (proposalPattern === "Wedge" && !proposalWedgeSubtype)
          : !onSubmitOwnerSignal || !signalIdentity || !snapshotRevision || !barsSha256 || !proposalDirection || proposalPattern !== "Wedge"))
      return;
    try {
      const content = JSON.stringify({ drawings, proposalPattern, proposalDirection, proposalWedgeSubtype, proposalNote, retrospectiveContext });
      if (proposalToken.current?.content !== content) {
        proposalToken.current = {
          content,
          key: globalThis.crypto?.randomUUID?.() ??
            `owner-proposal-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        };
      }
      setProposalPending(true);
      setProposalStatus("Сохранение сигнала…");
      const receipt = ownerChartMode
        ? await onSubmitOwnerChart!(buildOwnerChartDraftV3({
            symbol, timeframe, pattern: proposalPattern as OwnerChartPatternV3,
            formationMovement: proposalDirection as OwnerChartMovement,
            ...(proposalPattern === "Wedge" ? { wedgeSubtype: proposalWedgeSubtype as OwnerWedgeSubtype } : {}),
            drawings, frozenCandles: candles,
            note: proposalNote.trim(), idempotencyKey: proposalToken.current.key,
          }))
        : await onSubmitOwnerSignal!(buildOwnerSignalDraft({
            signalId: signalIdentity!, snapshotRevision: snapshotRevision!,
            barsSha256: barsSha256!, pattern: (proposalDirection === "UP" ? "Rising Wedge" : "Falling Wedge") as OwnerSignalDraft["pattern"],
            drawings, frozenCandles: candles,
            note: proposalNote.trim(), idempotencyKey: proposalToken.current.key,
            contextAsOfMs: retrospectiveContext?.asOfMs,
            contextBarsSha256: retrospectiveContext?.barsSha256,
          }));
      if (ownerChartMode) {
        setProposalStatus(
          `Пример ${receipt.proposalId.slice(0, 12)} сохранён в «Мои сигналы». ` +
          "Источник свечей — пользовательский, требует проверки на истории. " +
          "Scanner не обучался автоматически; торговый кандидат не создан.",
        );
        return;
      }
      const reasons: Record<string, string> = {
        ray_anchor_not_confirmed_pivot: "опорная точка не подтверждена Scanner",
        ray_pair_not_generated: "пара точек не формирует допустимую линию",
        ray_pair_filtered: "линия отклонена действующим фильтром",
        pivot_evaluation_budget_exceeded: "слишком много пивотов для быстрой проверки",
        robot_pattern_unsupported: "Robot не поддерживает этот паттерн",
        trusted_scanner_strategy_snapshot_required:
          "нужна дополнительная проверка стратегии, входа и защиты",
      };
      setProposalStatus(
        `Новый сигнал ${receipt.proposalId.slice(0, 12)} сохранён. ` +
        `${receipt.decision === "REJECTED" ? "Предварительно отклонён" : "Предварительная геометрия проверена"}: ` +
        `${reasons[receipt.reason] ?? "оценка требует дополнительной проверки"}. ` +
        "Торговый кандидат не создан.",
      );
    } catch (error) {
      setProposalStatus(`Не удалось сохранить: ${error instanceof Error ? error.message : "неизвестная ошибка"}`);
    } finally {
      setProposalPending(false);
    }
  };
  const applyFollowLatest = useCallback((next: boolean) => {
    followLatestRef.current = next;
  }, []);
  useEffect(() => {
    try {
      globalThis.localStorage?.setItem(storageKey, serializeDrawings(drawings));
    } catch {
      // Persisted review delivery is server-owned; a failed optional browser
      // drawing cache must not crash the Editor or alter feedback authority.
    }
  }, [drawings, storageKey]);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const css = getComputedStyle(document.documentElement),
      token = (name: string, fallback: string) =>
        css.getPropertyValue(name).trim() || fallback;
    const chart = createChart(host, {
      autoSize: true,
      localization: { locale: "ru-RU", timeFormatter: editorMoscowCrosshairTime },
      layout: {
        background: {
          type: ColorType.Solid,
          color: token("--chart-bg", "#10151b"),
        },
        textColor: token("--chart-text", "#8996a3"),
        fontSize: 9,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: token("--chart-grid", "#202830") },
        horzLines: { color: token("--chart-grid", "#202830") },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "#8996a3",
          width: 1,
          labelBackgroundColor: "#394653",
        },
        horzLine: {
          color: "#8996a3",
          width: 1,
          labelBackgroundColor: "#394653",
        },
      },
      rightPriceScale: {
        visible: true,
        borderColor: "#303b47",
        autoScale: true,
        minimumWidth: 0,
      },
      timeScale: {
        tickMarkFormatter: editorMoscowTickMark,
        visible: true,
        borderColor: "#303b47",
        timeVisible: true,
        rightOffset: DEFAULT_RIGHT_OFFSET_BARS,
        fixRightEdge: false,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: false,
        horzTouchDrag: false,
        vertTouchDrag: false,
      },
      handleScale: {
        mouseWheel: false,
        pinch: false,
        axisPressedMouseMove: false,
        axisDoubleClickReset: false,
      },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: token("--chart-bull", "#3bc639"),
      downColor: token("--chart-bear", "#cd0000"),
      borderVisible: false,
      wickUpColor: token("--chart-bull", "#3bc639"),
      wickDownColor: token("--chart-bear", "#cd0000"),
    });
    chartRef.current = chart;
    seriesRef.current = series;
    panBatcherRef.current = createFrameBatcher(
      requestAnimationFrame,
      cancelAnimationFrame,
    );
    const listener = () => {
      setRenderTick((v) => v + 1);
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(listener);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(listener);
      chart.remove();
      panBatcherRef.current?.cancel();
      panBatcherRef.current = null;
      chartRef.current = null;
      seriesRef.current = null;
      averageEntryLineRef.current = null;
      averageEntryLineSymbolRef.current = null;
    };
  }, []);
  useEffect(() => {
    const series = seriesRef.current;
    const timeScale = chartRef.current?.timeScale();
    if (!series || !timeScale) return;
    replaceSeriesDataPreservingViewport(
      candles.map((c, i) => ({
        time: candleTime(c, i),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
      followLatestRef.current,
      series,
      timeScale,
    );
    const previousCount = previousEditorBars.current;
    previousEditorBars.current = candles.length;
    if (editorMode && signalIdentity && !initialSourceFrameApplied.current) {
      const sourceRange = initialSourceGeometryRange(referenceDrawings);
      if (sourceRange) {
        timeScale.setVisibleLogicalRange(sourceRange);
        followLatestRef.current = false;
        initialSourceFrameApplied.current = true;
      }
    }
    // An explicit "Add later candles" action should reveal the newly closed
    // market context instead of silently leaving it far right off-screen.
    if (editorMode && previousCount !== null && candles.length > previousCount &&
        initialSourceFrameApplied.current) {
      const range = timeScale.getVisibleLogicalRange();
      const span = range ? Math.max(25, range.to - range.from) : 70;
      const to = candles.length + 6;
      timeScale.setVisibleLogicalRange({ from: to - span, to });
    }
    setRenderTick((v) => v + 1);
  }, [candles, editorMode, signalIdentity, referenceDrawings]);
  useEffect(() => {
    const priceFormat = tickSize === null ? null : chartPriceFormat(tickSize);
    if (priceFormat) seriesRef.current?.applyOptions({ priceFormat });
  }, [tickSize]);
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const price = Number(averageEntryPrice);
    const valid = averageEntryPrice !== null && Number.isFinite(price) && price > 0;
    if (
      averageEntryLineRef.current !== null &&
      (!valid || averageEntryLineSymbolRef.current !== symbol)
    ) {
      series.removePriceLine(averageEntryLineRef.current);
      averageEntryLineRef.current = null;
      averageEntryLineSymbolRef.current = null;
    }
    if (!valid) return;
    if (averageEntryLineRef.current === null) {
      averageEntryLineRef.current = series.createPriceLine({
        price,
        color: "#d7dce2",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        lineVisible: true,
        axisLabelVisible: true,
        title: "AVG",
        axisLabelColor: "#707780",
        axisLabelTextColor: "#f1f3f5",
      });
      averageEntryLineSymbolRef.current = symbol;
      return;
    }
    averageEntryLineRef.current.applyOptions({ price });
  }, [averageEntryPrice, symbol]);
  const drawingPriceFormatter = useMemo(() => {
    const format = tickSize === null ? null : chartPriceFormat(tickSize);
    return format?.formatter ?? ((price: number) => price.toFixed(4));
  }, [tickSize]);
  const coordinates = useMemo<DrawingCoordinates>(() => {
    void renderTick;
    return {
      logicalToX: (v) =>
        chartRef.current?.timeScale().logicalToCoordinate(v as never) ?? null,
      xToLogical: (v) =>
        chartRef.current?.timeScale().coordinateToLogical(v) ?? null,
      priceToY: (v) => seriesRef.current?.priceToCoordinate(v) ?? null,
      yToPrice: (v) => seriesRef.current?.coordinateToPrice(v) ?? null,
    };
  }, [renderTick]);
  const visibleRobotMarkers = useMemo(
    () => readOnly
      ? visibleRobotTradeMarkers(robotTradeMarkers, candles, timeframe)
      : [],
    [readOnly, robotTradeMarkers, candles, timeframe],
  );
  const robotMarkerShapes = visibleRobotMarkers.flatMap((marker, index) => {
    const x = coordinates.logicalToX(marker.logical);
    const y = coordinates.priceToY(marker.price);
    if (x === null || y === null || !Number.isFinite(x) || !Number.isFinite(y))
      return [];
    const color = marker.side === "Buy" ? TELEGRAM_BUY_COLOR : TELEGRAM_SELL_COLOR;
    const points = marker.side === "Buy"
      ? `${x},${y - 8} ${x - 7},${y + 6} ${x + 7},${y + 6}`
      : `${x},${y + 8} ${x - 7},${y - 6} ${x + 7},${y - 6}`;
    return [<polygon
      key={`${marker.logical}:${marker.price}:${marker.side}:${index}`}
      points={points} fill={marker.filled ? color : "none"}
      stroke={marker.filled ? "#000000" : color}
      strokeWidth={marker.filled ? 0.8 : 1.8}
    />];
  });
  const relative = (event: { clientX: number; clientY: number }) => {
    const r = hostRef.current?.getBoundingClientRect();
    return r ? { x: event.clientX - r.left, y: event.clientY - r.top } : null;
  };
  const targetsPendingLimitLine = (target: EventTarget | null) =>
    target instanceof Element &&
    target.closest("[data-pending-limit-line], [data-active-limit-line], [data-protection-line], [data-chart-control]") !== null;
  const clearCrosshairTimer = () => {
    if (touchCrosshair.current.timer) {
      clearTimeout(touchCrosshair.current.timer);
      touchCrosshair.current.timer = null;
    }
  };
  const updateCrosshair = (point: { x: number; y: number }) => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;
    const logical = chart.timeScale().coordinateToLogical(point.x);
    const price = series.coordinateToPrice(point.y);
    const index = logical === null
      ? -1
      : Math.max(0, Math.min(candles.length - 1, Math.round(logical)));
    if (price !== null && candles[index]) {
      chart.setCrosshairPosition(
        price,
        candleTime(candles[index], index),
        series,
      );
    }
  };
  useEffect(() => () => clearCrosshairTimer(), []);
  const beginPinch = () => {
    const chart = chartRef.current,
      series = seriesRef.current,
      values = [...pointers.current.entries()];
    if (!chart || !series || values.length !== 2) return;
    const [[id1, a], [id2, b]] = values,
      xRange = chart.timeScale().getVisibleLogicalRange(),
      priceRange = chart.priceScale("right").getVisibleRange(),
      logical = chart.timeScale().coordinateToLogical((a.x + b.x) / 2),
      price = series.coordinateToPrice((a.y + b.y) / 2);
    if (xRange && priceRange && logical !== null && price !== null)
      gesture.current = {
        type: "pinch",
        ids: [id1, id2],
        dx: Math.abs(b.x - a.x),
        dy: Math.abs(b.y - a.y),
        logical,
        price,
        xRange,
        priceRange,
      };
  };
  const fastLimitPriceAtY = (y: number) => {
    const direct = seriesRef.current?.coordinateToPrice(y);
    if (direct !== null && direct !== undefined) return direct;
    const range = chartRef.current?.priceScale("right").getVisibleRange();
    const plotHeight = (hostRef.current?.clientHeight ?? 0) - TIME_SCALE_HEIGHT;
    if (!range || plotHeight <= 0) return null;
    const ratio = Math.max(0, Math.min(1, y / plotHeight));
    return range.to - ratio * (range.to - range.from);
  };
  const activeLimitEdit = useActiveLimitEdit({
    priceAtClientY: (clientY) => {
      const host = hostRef.current;
      if (!host) return null;
      const price = fastLimitPriceAtY(clientY - host.getBoundingClientRect().top);
      return price === null ? null : String(price);
    },
    normalizePrice: (price, side) =>
      normalizeLimitDraftPrice(price, tickSize === null ? null : String(tickSize), side),
    amend: async (orderId, price) => {
      if (!onActiveLimitAmend) throw new Error("active Limit amend unavailable");
      await onActiveLimitAmend(orderId, price);
    },
    cancelOrder: async (orderId) => {
      if (!onActiveLimitCancel) throw new Error("active Limit cancel unavailable");
      await onActiveLimitCancel(orderId);
    },
  });
  const onPointerDown = (event: React.PointerEvent) => {
    if (targetsPendingLimitLine(event.target)) return;

    const p = relative(event);
    if (!p) return;

    if (fastLimitActive && onFastLimitPriceSelect) {
      const price = fastLimitPriceAtY(p.y);
      if (price !== null && price !== undefined) {
        event.preventDefault();
        onFastLimitPriceSelect(String(price));
        return;
      }
    }
    pointers.current.set(event.pointerId, p);
    event.currentTarget.setPointerCapture(event.pointerId);
    if (pointers.current.size === 2) {
      clearCrosshairTimer();
      touchCrosshair.current.state = { mode: "IDLE" };
      beginPinch();
      return;
    }
    const chart = chartRef.current;
    if (!chart) return;
    const xr = chart.timeScale().getVisibleLogicalRange(),
      pr = chart.priceScale("right").getVisibleRange(),
      width = hostRef.current?.clientWidth ?? 0,
      height = hostRef.current?.clientHeight ?? 0;
    if (!xr || !pr) return;
    if (
      p.x >
      width - (chart.priceScale("right").width() || PRICE_SCALE_WIDTH_FALLBACK)
    )
      gesture.current = {
        type: "axis-y",
        id: event.pointerId,
        startX: p.x,
        startY: p.y,
        xRange: xr,
        priceRange: pr,
      };
    else if (p.y > height - TIME_SCALE_HEIGHT)
      gesture.current = {
        type: "axis-x",
        id: event.pointerId,
        startX: p.x,
        startY: p.y,
        xRange: xr,
        priceRange: pr,
      };
    else if (tool === "select") {
      if (chart.timeScale().coordinateToLogical(p.x) !== null) {
        gesture.current = {
          type: "plot-pan",
          id: event.pointerId,
          startX: p.x,
          startY: p.y,
          xRange: xr,
          priceRange: pr,
        };
        if (event.pointerType === "touch") {
          if (touchCrosshair.current.state.mode === "PINNED") {
            chart.clearCrosshairPosition();
          }
          clearCrosshairTimer();
          touchCrosshair.current = {
            state: { mode: "PENDING", start: p },
            pointerId: event.pointerId,
            last: p,
            timer: setTimeout(() => {
              const current = touchCrosshair.current;
              current.state = activateTouchCrosshair(current.state);
              current.timer = null;
              if (current.state.mode === "INSPECTING" && current.last) {
                gesture.current = null;
                updateCrosshair(current.last);
              }
            }, CROSSHAIR_HOLD_MS),
          };
        }
      }
    }
  };
  const onPointerMove = (event: React.PointerEvent) => {
    if (targetsPendingLimitLine(event.target)) return;
    const p = relative(event),
      chart = chartRef.current;
    if (!p || !chart) return;
    if (tool === "select" && event.pointerType !== "touch") {
      updateCrosshair(p);
    }
    const touch = touchCrosshair.current;
    if (event.pointerType === "touch" && touch.pointerId === event.pointerId) {
      touch.last = p;
      const next = moveTouchCrosshair(touch.state, p);
      if (touch.state.mode === "PENDING" && next.mode === "PANNING") {
        clearCrosshairTimer();
      }
      touch.state = next;
      if (next.mode === "PENDING") return;
      if (next.mode === "INSPECTING") {
        updateCrosshair(p);
        event.preventDefault();
        return;
      }
    }
    if (!pointers.current.has(event.pointerId)) return;
    pointers.current.set(event.pointerId, p);
    const g = gesture.current;
    if (g?.type === "pinch") {
      const a = pointers.current.get(g.ids[0]),
        b = pointers.current.get(g.ids[1]);
      if (!a || !b) return;
      const d = calculateDirectionalPinch(
        g.dx,
        g.dy,
        Math.abs(b.x - a.x),
        Math.abs(b.y - a.y),
      );
      if (d.axes === "X" || d.axes === "XY") {
        chart
          .timeScale()
          .setVisibleLogicalRange(
            scaleRangeAroundAnchor(
              g.xRange.from,
              g.xRange.to,
              g.logical,
              d.xScale,
            ),
          );
        applyFollowLatest(false);
      }
      if (d.axes === "Y" || d.axes === "XY") {
        chart.priceScale("right").setAutoScale(false);
        chart
          .priceScale("right")
          .setVisibleRange(
            scaleRangeAroundAnchor(
              g.priceRange.from,
              g.priceRange.to,
              g.price,
              d.yScale,
            ),
          );
      }
      event.preventDefault();
    } else if (g?.type === "axis-y" && g.id === event.pointerId) {
      const scale = Math.exp((g.startY - p.y) / 140),
        anchor = (g.priceRange.from + g.priceRange.to) / 2;
      chart.priceScale("right").setAutoScale(false);
      chart
        .priceScale("right")
        .setVisibleRange(
          scaleRangeAroundAnchor(
            g.priceRange.from,
            g.priceRange.to,
            anchor,
            scale,
          ),
        );
      event.preventDefault();
    } else if (g?.type === "axis-x" && g.id === event.pointerId) {
      const scale = Math.exp((p.x - g.startX) / 160),
        anchor = (g.xRange.from + g.xRange.to) / 2;
      chart
        .timeScale()
        .setVisibleLogicalRange(
          scaleRangeAroundAnchor(g.xRange.from, g.xRange.to, anchor, scale),
        );
      applyFollowLatest(false);
      event.preventDefault();
    } else if (g?.type === "plot-pan" && g.id === event.pointerId) {
      const plotWidth = Math.max(
        1,
        (hostRef.current?.clientWidth ?? 1)
          - (chart.priceScale("right").width() || PRICE_SCALE_WIDTH_FALLBACK),
      );
      const logicalRange = translateLogicalRangeByPixels(
        g.xRange,
        p.x - g.startX,
        plotWidth,
      );
      const deltaY = p.y - g.startY;
      panBatcherRef.current?.schedule(() => {
        chart.timeScale().setVisibleLogicalRange(logicalRange);
        if (deltaY !== 0) {
          chart.priceScale("right").setAutoScale(false);
          chart.priceScale("right").setVisibleRange(
            translatePriceRangeByPixels(
              g.priceRange,
              deltaY,
              Math.max(1, (hostRef.current?.clientHeight ?? 1) - TIME_SCALE_HEIGHT),
            ),
          );
        }
      });
      applyFollowLatest(false);
      event.preventDefault();
    }
  };
  const endPointer = (event: React.PointerEvent) => {
    if (targetsPendingLimitLine(event.target)) return;
    pointers.current.delete(event.pointerId);
    if (touchCrosshair.current.pointerId === event.pointerId) {
      clearCrosshairTimer();
      touchCrosshair.current.state = releaseTouchCrosshair(
        touchCrosshair.current.state,
      );
      touchCrosshair.current.pointerId = null;
      touchCrosshair.current.last = null;
    }
    gesture.current = null;
  };
  const onWheel = (event: React.WheelEvent) => {
    const chart = chartRef.current,
      series = seriesRef.current,
      p = relative(event);
    if (!chart || !series || !p) return;
    const xr = chart.timeScale().getVisibleLogicalRange(),
      logical = chart.timeScale().coordinateToLogical(p.x);
    if (!xr || logical === null) return;
    const factor = Math.exp(-event.deltaY * 0.0015);
    chart
      .timeScale()
      .setVisibleLogicalRange(
        scaleRangeAroundAnchor(xr.from, xr.to, logical, factor),
      );
    applyFollowLatest(false);
    if (event.ctrlKey) {
      const pr = chart.priceScale("right").getVisibleRange(),
        price = series.coordinateToPrice(p.y);
      if (pr && price !== null) {
        chart.priceScale("right").setAutoScale(false);
        chart
          .priceScale("right")
          .setVisibleRange(
            scaleRangeAroundAnchor(pr.from, pr.to, price, factor),
          );
      }
    }
    event.preventDefault();
  };
  const resetAuto = () => {
      chartRef.current?.priceScale("right").setAutoScale(true);
    },
    resetHorizontalView = () => {
      const timeScale = chartRef.current?.timeScale();
      if (!timeScale) return;
      applyFollowLatest(true);
      timeScale.applyOptions({ rightOffset: DEFAULT_RIGHT_OFFSET_BARS });
      timeScale.scrollToRealTime();
    };
  const visiblePendingLimitDrafts =
    pendingLimitDrafts ??
    (pendingLimitDraft ? [pendingLimitDraft] : []);
  const hasVisibleLimitCandidates =
    visiblePendingLimitDrafts.length > 0 ||
    activeLimitEdit.activeCandidate !== null;
  const deleteSelected = useCallback(() => {
    if (selectedId) {
      commit(drawings.filter((d) => d.id !== selectedId));
      setSelectedId(null);
    }
  }, [commit, drawings, selectedId]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      // This listener is global: typing or deleting an owner review note (or
      // another workspace form value) must never delete a selected chart ray.
      const target = event.target;
      if (event.isComposing || (target instanceof Element && target.closest(
        "input, textarea, select, button, [contenteditable], [role='textbox'], [role='combobox']",
      ))) return;
      if (event.key === "Delete" || event.key === "Backspace") deleteSelected();
      if (event.key === "Escape") {
        setSelectedId(null);
        setTool("select");
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [deleteSelected]);
  return (
    <section
      className={`chart-panel workspace-panel${positionFooter ? " has-position-footer" : ""}`}
      aria-label="Candlestick chart"
    >
      <div className="chart-content-row">
        {editorMode && (signalIdentity || ownerChartMode) && (
          <div className="editor-correction-export">
            <div className="editor-review-topline">
              <nav className="editor-workspace-shortcuts" aria-label="Переход между вкладками">
                <button type="button" aria-label="Терминал" title="Терминал"
                  onClick={() => onEditorNavigate?.("TERMINAL")}>
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <line x1="12" x2="12" y1="2" y2="22" />
                    <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                  </svg>
                </button>
                <button type="button" aria-label="Автопилот" title="Автопилот"
                  onClick={() => onEditorNavigate?.("AUTOPILOT")}>
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" />
                    <circle cx="12" cy="12" r="2.2" />
                    <line x1="4.5" y1="9.5" x2="10.2" y2="11.3" />
                    <line x1="19.5" y1="9.5" x2="13.8" y2="11.3" />
                    <line x1="12" y1="14.2" x2="12" y2="20.5" />
                    <path d="M4.8 9.8 Q12 6.5 19.2 9.8" />
                  </svg>
                </button>
              </nav>
            </div>
            <small aria-label="Название исходного сигнала">{ownerChartMode ? "Мой сигнал · закрытые свечи, источник не проверен" : `Исходный сигнал: ${originalPattern ?? "тип неизвестен"}`}</small>
            {newSignalMode && <strong className="editor-new-signal-title">Создать новый сигнал</strong>}
            {!ownerChartMode && <button type="button" disabled={extensionPending || reviewPending || proposalPending}
              onClick={() => {
                if (!onExtendEditorHistory) return;
                setExtensionPending(true);
                setExtensionStatus("Загружаются следующие закрытые свечи…");
                void onExtendEditorHistory()
                  .then(() => setExtensionStatus("Поздние свечи добавлены"))
                  .catch((error) => setExtensionStatus(
                    `Не удалось получить поздние свечи: ${error instanceof Error ? error.message : "ошибка"}`,
                  ))
                  .finally(() => setExtensionPending(false));
              }}>
              {extensionPending ? "Загрузка…" : "Показать следующие свечи"}
            </button>}
            {!ownerChartMode && <button type="button" disabled={extensionPending || reviewPending || proposalPending
                || !onShowCurrentEditorChart}
              onClick={() => onShowCurrentEditorChart?.()}>
              Показать актуальный график
            </button>}
            {!ownerChartMode && !newSignalMode && <button type="button" disabled={extensionPending || reviewPending || proposalPending}
              aria-pressed={false} onClick={switchSignalDrawingMode}>
              Создать новый сигнал
            </button>}
            {newSignalMode ? (
              <>
                <select aria-label="Тип нового сигнала" value={proposalPattern}
                  onChange={(event) => {
                    const pattern = event.target.value as OwnerChartPatternV3;
                    setProposalPattern(pattern);
                    setProposalWedgeSubtype("");
                    setProposalStatus("");
                    proposalHistoryRef.current = new DrawingHistory([]);
                    historyRef.current = proposalHistoryRef.current;
                    setDrawings([]);
                    setTool("crosshair");
                  }}>
                  <option value="" disabled>Выберите паттерн</option>
                  <option value="Wedge">Клин</option>
                  <option value="Ikigai Box">Коробка</option>
                  <option value="Triangle">Треугольник</option>
                  <option value="Double Top/Bottom">Двойная вершина / дно</option>
                  <option value="Head and Shoulders">Голова и плечи</option>
                  <option value="G-Shaped">Г-образный паттерн</option>
                </select>
                <select aria-label="Направление движения графика" value={proposalDirection}
                  onChange={(event) => { setProposalDirection(event.target.value as OwnerChartMovement); setProposalStatus(""); }}>
                  <option value="" disabled>Направление движения</option>
                  <option value="UP">↑ Вверх</option>
                  <option value="DOWN">↓ Вниз</option>
                </select>
                {proposalPattern === "Wedge" && (
                  <select aria-label="Подтип клина" value={proposalWedgeSubtype}
                    onChange={(event) => { setProposalWedgeSubtype(event.target.value as OwnerWedgeSubtype); setProposalStatus(""); }}>
                    <option value="" disabled>Подтип клина</option>
                    <option value="SLOWDOWN">Замедление</option>
                    <option value="CORRECTION">Коррекционный</option>
                  </select>
                )}
                <input aria-label="Комментарий к новому сигналу"
                  placeholder="Комментарий (необязательно)" maxLength={1024}
                  value={proposalNote} onChange={(event) => { setProposalNote(event.target.value); setProposalStatus(""); }} />
                <button type="button" disabled={proposalPending || (ownerChartMode
                    ? !onSubmitOwnerChart || !proposalPattern || !proposalDirection
                    : !onSubmitOwnerSignal)}
                  title={proposalStatus || undefined}
                  onClick={() => void submitOwnerProposal()}>
                  {proposalPending ? "Сохранение…" :
                    proposalStatus.startsWith("Не удалось сохранить:") ? "Ошибка сохранения — повторить" :
                    proposalStatus.startsWith("Пример ") ? "Пример сохранён в «Мои сигналы»" :
                    "Сохранить сигнал"}
                </button>
                {!ownerChartMode && <button type="button" className="editor-return-to-correction"
                  disabled={proposalPending || reviewPending} onClick={switchSignalDrawingMode}>
                  <span aria-hidden="true">←</span> Вернуться к исправлению
                </button>}
              </>
            ) : (
              <>
            <select
              aria-label="Оценка сигнала"
              value={reviewLabel}
              onChange={(event) => { setReviewLabel(event.target.value as GeometryReviewDraft["label"]); markReviewEdited(); }}
            >
              <option value="GEOMETRY_CORRECTED">Исправлена геометрия</option>
              <option value="CONFIRMED">Верный сигнал</option>
              <option value="FALSE_POSITIVE">Ложный сигнал</option>
              <option value="UNCERTAIN">Неоднозначно</option>
            </select>
            <input
              aria-label="Комментарий к исправлению"
              placeholder="Комментарий (необязательно)"
              maxLength={1024}
              value={reviewNote}
              onChange={(event) => { setReviewNote(event.target.value); markReviewEdited(); }}
            />
            <button type="button" disabled={reviewPending || !snapshotRevision || !barsSha256 || !onSaveGeometryReview}
              title={reviewStatus.startsWith("Не удалось сохранить:") ? reviewStatus : undefined}
              onClick={() => void saveCorrection()}>
              {reviewPending ? "Сохранение…" : reviewStatus.startsWith("Не удалось сохранить:") ? "Не удалось сохранить" : "Передать исправление"}
            </button>
            {reviewStatus === "Исправлена геометрия" && !reviewDirty && (
              <output className="editor-review-success" role="status" aria-live="polite">
                Исправлена геометрия
              </output>
            )}
              </>
            )}
          </div>
        )}
        <DrawingToolbar
          activeTool={tool}
          magnet={magnet}
          selected={selectedId !== null}
          onTool={setTool}
          onMagnet={() => setMagnet((v) => !v)}
          onUndo={() => {
            const previous = drawings;
            const undone = historyRef.current.undo();
            if (undone !== previous) {
              setDrawings(undone);
              if (!newSignalMode) markReviewEdited();
            }
          }}
          onDelete={deleteSelected}
          onClear={() => {
            if (drawings.length) setClearConfirmationOpen(true);
          }}
        />
      <div
        className="chart-stage"
        role="application"
        aria-label="Interactive market chart"
        onPointerDownCapture={onPointerDown}
        onPointerMoveCapture={onPointerMove}
        onPointerUpCapture={endPointer}
        onPointerCancelCapture={endPointer}
        onLostPointerCapture={endPointer}
        onPointerLeave={() => {
          if (touchCrosshair.current.state.mode !== "PINNED") {
            chartRef.current?.clearCrosshairPosition();
          }
        }}
        onWheel={onWheel}
        onDoubleClick={(e) => {
          const p = relative(e);
          const chart = chartRef.current;
          const host = hostRef.current;
          if (!p || !chart || !host) return;
          const target = chartAxisTarget(
            p,
            host.clientWidth,
            host.clientHeight,
            chart.priceScale("right").width() || PRICE_SCALE_WIDTH_FALLBACK,
            TIME_SCALE_HEIGHT,
          );
          if (target === "TIME") resetHorizontalView();
          else if (target === "PRICE")
            resetAuto();
        }}
      >
        {workspaceControls}
        <div ref={hostRef} className="chart-engine" />
        {!editorMode && (() => {
          const last = candles[candles.length - 1];
          const status = candleCloseStatus(last?.time, timeframe, candleClockMs);
          if (status.status === "UNAVAILABLE") return null;
          const priceY = last ? coordinates.priceToY(last.close) : null;
          if (priceY === null || !Number.isFinite(priceY)) return null;
          const height = hostRef.current?.clientHeight ?? 0;
          if (priceY < 0 || priceY > height - TIME_SCALE_HEIGHT - 19) return null;
          return (
            <span className={"chart-candle-close" + (status.status === "STALE" ? " stale" : "")}
              aria-label={status.status === "STALE" ? "Свечи устарели" : "До закрытия свечи: " + status.label}
              style={{ top: priceY + 14, width: chartRef.current?.priceScale("right").width() || PRICE_SCALE_WIDTH_FALLBACK }}
              title={status.status === "STALE" ? "Актуальность потока свечей не подтверждена" : "Осталось до закрытия текущей свечи"}>
              {status.label}
            </span>
          );
        })()}
        {robotMarkerShapes.length > 0 ? (
          <svg className="robot-execution-marker-layer" aria-label="Маркеры исполнений робота"
            aria-hidden="true" viewBox={`0 0 ${hostRef.current?.clientWidth ?? 1} ${hostRef.current?.clientHeight ?? 1}`}
            preserveAspectRatio="none">
            {robotMarkerShapes}
          </svg>
        ) : null}
        <DrawingOverlay
          drawings={drawings}
          referenceDrawings={referenceDrawings}
          selectedId={selectedId}
          tool={tool}
          magnet={magnet}
          candles={candles}
          candleAligned={editorMode && signalIdentity !== null}
          priceScaleWidth={chartRef.current?.priceScale("right").width() || PRICE_SCALE_WIDTH_FALLBACK}
          coordinates={coordinates}
          priceFormatter={drawingPriceFormatter}
          onCommit={commit}
          onSelect={setSelectedId}
          onDrawingComplete={() => setTool("select")}
          onDrawingGesture={() => {
            gesture.current = null;
          }}
        />
        {(() => {
          const displayedPrice = stopDraft?.price ?? authoritativeStopPrice;
          if (displayedPrice === null) return null;
          const numericPrice = Number(displayedPrice);
          if (!Number.isFinite(numericPrice)) return null;
          return (
            <StopLine
              price={displayedPrice}
              top={coordinates.priceToY(numericPrice)}
              rightOffset={
                chartRef.current?.priceScale("right").width() ||
                PRICE_SCALE_WIDTH_FALLBACK
              }
              mode={stopDraft?.mode ?? "ACTIVE"}
              submitting={stopDraft?.status === "submitting"}
              onDragClientY={(clientY) => {
                const host = hostRef.current;
                const series = seriesRef.current;
                if (!host || !series || !onStopDraftPriceChange) return;
                const price = series.coordinateToPrice(
                  clientY - host.getBoundingClientRect().top,
                );
                if (price !== null) onStopDraftPriceChange(String(price));
              }}
              onConfirm={() => void onStopConfirm?.()}
              onCancel={onStopCancelDraft}
              onEdit={onStopEdit}
              onDelete={() => void onStopDelete?.()}
              readOnly={readOnly}
            />
          );
        })()}
        {(() => {
          const displayedPrice = takeDraft?.price ?? authoritativeTakePrice;
          if (displayedPrice === null) return null;
          const numericPrice = Number(displayedPrice);
          if (!Number.isFinite(numericPrice)) return null;
          return (
            <StopLine
              leg="TAKE"
              price={displayedPrice}
              top={coordinates.priceToY(numericPrice)}
              rightOffset={
                chartRef.current?.priceScale("right").width() ||
                PRICE_SCALE_WIDTH_FALLBACK
              }
              mode={takeDraft?.mode ?? "ACTIVE"}
              submitting={takeDraft?.status === "submitting"}
              onDragClientY={(clientY) => {
                const host = hostRef.current;
                const series = seriesRef.current;
                if (!host || !series || !onTakeDraftPriceChange) return;
                const price = series.coordinateToPrice(
                  clientY - host.getBoundingClientRect().top,
                );
                if (price !== null) onTakeDraftPriceChange(String(price));
              }}
              onConfirm={() => void onTakeConfirm?.()}
              onCancel={onTakeCancelDraft}
              onEdit={onTakeEdit}
              onDelete={() => void onTakeDelete?.()}
              readOnly={readOnly}
            />
          );
        })()}
        {activeLimitOrders.map((order) => {
          const editState = activeLimitEdit.state;
          const selected = editState.mode !== "ACTIVE" && editState.orderId === order.order_id;
          const editing = selected && (
            editState.mode === "EDITING" ||
            editState.mode === "PENDING_CONFIRM" ||
            editState.mode === "AMENDING" ||
            (editState.mode === "CANCELLING" && editState.presentation === "EDIT")
          );
          const activeCancelVisible = selected && (
            editState.mode === "ACTIVE_CANCEL" ||
            (editState.mode === "CANCELLING" && editState.presentation === "ACTIVE")
          );
          const displayedPrice = editState.mode !== "ACTIVE" && editing
            ? editState.candidatePrice
            : order.price;
          const price = Number(displayedPrice);
          if (!Number.isFinite(price)) return null;

          const top = coordinates.priceToY(price);
          if (top === null) return null;

          return (
            <div
              key={order.order_id}
              className={`active-limit-line ${order.side.toLowerCase()} ${editing ? "editing" : ""}`}
              aria-label={`Active ${order.side} Limit at ${displayedPrice}`}
              data-active-limit-line
              data-active-limit-edit={order.order_id}
              onPointerDown={readOnly ? undefined : (event) => activeLimitEdit.pointerDown(event, order)}
              onPointerMove={readOnly ? undefined : activeLimitEdit.pointerMove}
              onPointerUp={readOnly ? undefined : activeLimitEdit.pointerUp}
              onPointerCancel={readOnly ? undefined : activeLimitEdit.pointerCancel}
              style={{
                top,
                right:
                  chartRef.current?.priceScale("right").width() ||
                  PRICE_SCALE_WIDTH_FALLBACK,
              }}
            >
              <span>{displayedPrice}</span>
              {!readOnly && editing && (activeLimitEdit.state.mode === "PENDING_CONFIRM" || activeLimitEdit.state.mode === "AMENDING" || activeLimitEdit.state.mode === "CANCELLING") ? (
                <div className="active-limit-actions">
                  <TradingControlButton className="active-limit-confirm" aria-label={`Confirm amend ${order.order_id}`} onTap={() => void activeLimitEdit.confirm()} disabled={activeLimitEdit.state.mode !== "PENDING_CONFIRM"}>✓</TradingControlButton>
                  <TradingControlButton className="active-limit-dismiss" aria-label={`Cancel Limit ${order.order_id}`} onTap={() => void activeLimitEdit.cancel().catch(() => {})} disabled={activeLimitEdit.state.mode !== "PENDING_CONFIRM"}>×</TradingControlButton>
                </div>
              ) : null}
              {!readOnly && activeCancelVisible ? (
                <div className="active-limit-actions">
                  <TradingControlButton className="active-limit-dismiss" aria-label={`Cancel Limit ${order.order_id}`} onTap={() => void activeLimitEdit.cancel().catch(() => {})} disabled={activeLimitEdit.state.mode !== "ACTIVE_CANCEL"}>×</TradingControlButton>
                </div>
              ) : null}
            </div>
          );
        })}
        {visiblePendingLimitDrafts.map((draft) => {
          const normalizedPrice = normalizedLimitDraftPrice(draft);
          if (normalizedPrice === null) return null;

          const top = coordinates.priceToY(Number(normalizedPrice));
          const selected = pendingLimitDraft?.draftId === draft.draftId;

          return (
            <PendingLimitLine
              key={draft.draftId}
              side={draft.side}
              price={normalizedPrice}
              top={top}
              rightOffset={
                chartRef.current?.priceScale("right").width() ||
                PRICE_SCALE_WIDTH_FALLBACK
              }
              selected={selected}
              controlsVisible
              popupLinked={draft.origin === "limits-popup"}
              onSelect={() => onPendingLimitSelect?.(draft.draftId)}
              onDismiss={() => onPendingLimitDismiss?.(draft.draftId)}
              onDragClientY={(clientY) => {
                const host = hostRef.current;
                const series = seriesRef.current;
                if (!host || !series || !onPendingLimitPriceChange) return;

                const price = series.coordinateToPrice(
                  clientY - host.getBoundingClientRect().top,
                );

                if (price !== null) {
                  onPendingLimitPriceChange(String(price), draft.draftId);
                }
              }}
              onConfirm={() => onPendingLimitConfirm?.(draft.draftId)}
              liveSubmitStatus={liveLimitDrafts && (draft.status === "submitting" || draft.status === "ambiguous")
                ? draft.status : undefined}
              rejectionReason={liveLimitDrafts && draft.status === "rejected"
                ? draft.rejectionReason : null}
              confirmDisabled={
                !pendingLimitVolumeValid[draft.side] ||
                draft.status === "submitting" ||
                draft.status === "ambiguous"
              }
            />
          );
        })}
        {hasVisibleLimitCandidates ? (
          <div className="pending-limit-batch-actions" data-active-limit-global-actions>
            <button
              type="button"
              className="pending-limit-batch-confirm"
              aria-label="Confirm all pending Limit drafts"
              onClick={() => setConfirmAllPendingOpen(true)}
            >
              {"\u2713"}
            </button>
            <button
              type="button"
              className="pending-limit-batch-dismiss"
              aria-label="Dismiss all pending Limit drafts"
              onClick={() => setDismissAllPendingOpen(true)}
            >
              &times;
            </button>
          </div>
        ) : null}

        {confirmAllPendingOpen ? (
          <div
            className="pending-limit-batch-confirmation submit-all"
            data-active-limit-global-actions
            onClick={() => setConfirmAllPendingOpen(false)}
          >
            <div
              className="pending-limit-batch-confirmation-card"
              style={{
                position: "absolute",
                right: "calc(64px + 2.6rem)",
                bottom: "3.4rem",
              }}
              onClick={(event) => event.stopPropagation()}
            >
              <strong>Confirm all pending limits?</strong>
              <div>
                <button
                  type="button"
                  className="confirm-all"
                  onClick={async () => {
                    const draftIds = visiblePendingLimitDrafts.map(
                      (draft) => draft.draftId,
                    );
                    const activeCandidate = activeLimitEdit.activeCandidate;
                    setConfirmAllPendingOpen(false);
                    await confirmVisibleLimitCandidates({
                      draftIds,
                      activeCandidate,
                      confirmDraft: (draftId) => onPendingLimitConfirm?.(draftId),
                      confirmEditedActive: () => activeLimitEdit.confirm(),
                    });
                  }}
                >
                  CONFIRM ALL
                </button>
                <button
                  type="button"
                  className="neutral"
                  onClick={() => setConfirmAllPendingOpen(false)}
                >
                  CANCEL
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {dismissAllPendingOpen ? (
          <div
            className="pending-limit-batch-confirmation dismiss-all"
            data-active-limit-global-actions
            onClick={() => setDismissAllPendingOpen(false)}
          >
            <div
              className="pending-limit-batch-confirmation-card"
              onClick={(event) => event.stopPropagation()}
            >
              <strong>Delete all pending limits?</strong>
              <div>
                <button
                  type="button"
                  className="danger"
                  onClick={() => {
                    // Read current render state at confirmation, not when the dialog opens.
                    const dismissibleDrafts = visiblePendingLimitDrafts.filter(
                      (draft) => !liveLimitDrafts || (
                        draft.status !== "submitting" && draft.status !== "ambiguous"
                      ),
                    );
                    const draftIds = dismissibleDrafts.map(
                      (draft) => draft.draftId,
                    );
                    const activeCandidate = activeLimitEdit.activeCandidate;
                    setDismissAllPendingOpen(false);
                    void cancelVisibleLimitCandidates({
                      draftIds,
                      activeCandidate,
                      dismissDrafts: () => {
                        for (const draft of dismissibleDrafts) {
                          onPendingLimitDismiss?.(draft.draftId);
                        }
                      },
                      cancelEditedActive: () => activeLimitEdit.cancel(),
                    }).catch(() => {});
                  }}
                >
                  DELETE ALL
                </button>
                <button
                  type="button"
                  className="neutral"
                  onClick={() => setDismissAllPendingOpen(false)}
                >
                  KEEP
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {clearConfirmationOpen ? (
          <DrawingClearConfirmation
            onCancel={() => setClearConfirmationOpen(false)}
            onConfirm={() => {
              setDrawings(clearDrawingHistory(historyRef.current));
              if (!newSignalMode) markReviewEdited();
              setSelectedId(null);
              setClearConfirmationOpen(false);
            }}
          />
        ) : null}
      </div>
      </div>
      {positionFooter}
    </section>
  );
}
