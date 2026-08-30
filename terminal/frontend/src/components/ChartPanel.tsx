import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
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
import { createFrameBatcher } from "../chart/frameBatcher";
import type { Candle } from "../contracts/marketData";
import type { PaperLimitOrder } from "../contracts/trading";
import type { LimitDraft } from "../orders/limitDraft";
import { normalizedLimitDraftPrice } from "../orders/limitDraft";
import { PendingLimitLine } from "../chart/PendingLimitLine";
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
  onPendingLimitSelect,
  onPendingLimitDismiss,
  onPendingLimitDismissAll,
  onPendingLimitPriceChange,
  onPendingLimitConfirm,
  fastLimitActive = false,
  onFastLimitPriceSelect,
  onActiveLimitAmend,
  onActiveLimitCancel,
  workspaceControls,
}: {
  candles: readonly Candle[];
  tickSize: number | null;
  symbol?: string;
  timeframe?: string;
  activeLimitOrders?: readonly PaperLimitOrder[];
  pendingLimitDraft?: LimitDraft | null;
  pendingLimitDrafts?: readonly LimitDraft[];
  onPendingLimitSelect?: (draftId: string) => void;
  onPendingLimitDismiss?: (draftId: string) => void;
  onPendingLimitDismissAll?: () => void;
  onPendingLimitPriceChange?: (price: string, draftId?: string) => void;
  onPendingLimitConfirm?: (draftId?: string) => void | Promise<void>;
  fastLimitActive?: boolean;
  onFastLimitPriceSelect?: (price: string) => void;
  onActiveLimitAmend?: (orderId: string, price: string) => Promise<void>;
  onActiveLimitCancel?: (orderId: string) => Promise<unknown>;
  workspaceControls?: ReactNode;
}) {
  const hostRef = useRef<HTMLDivElement>(null),
    chartRef = useRef<IChartApi | null>(null),
    seriesRef = useRef<Series | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>()),
    gesture = useRef<Gesture>(null);
  const touchCrosshair = useRef<{
    state: TouchCrosshairState;
    pointerId: number | null;
    last: { x: number; y: number } | null;
    timer: ReturnType<typeof setTimeout> | null;
  }>({ state: { mode: "IDLE" }, pointerId: null, last: null, timer: null });
  const followLatestRef = useRef(true);
  const panBatcherRef = useRef<ReturnType<typeof createFrameBatcher> | null>(null);
  const [renderTick, setRenderTick] = useState(0),
    [tool, setTool] = useState<DrawingTool>("select"),
    [magnet, setMagnet] = useState(false),
    [selectedId, setSelectedId] = useState<string | null>(null),
    [clearConfirmationOpen, setClearConfirmationOpen] = useState(false),
    [confirmAllPendingOpen, setConfirmAllPendingOpen] = useState(false),
    [dismissAllPendingOpen, setDismissAllPendingOpen] = useState(false);
  const storageKey = `bybitscanner:drawings:v1:${symbol}:${timeframe}`;
  const historyRef = useRef(
    new DrawingHistory(
      deserializeDrawings(globalThis.localStorage?.getItem(storageKey) ?? null),
    ),
  );
  const [drawings, setDrawings] = useState<DrawingObject[]>(
    historyRef.current.current,
  );
  const commit = useCallback((next: DrawingObject[]) => {
    historyRef.current.commit(next);
    setDrawings(next);
  }, []);
  const applyFollowLatest = useCallback((next: boolean) => {
    followLatestRef.current = next;
  }, []);
  useEffect(() => {
    globalThis.localStorage?.setItem(storageKey, serializeDrawings(drawings));
  }, [drawings, storageKey]);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const css = getComputedStyle(document.documentElement),
      token = (name: string, fallback: string) =>
        css.getPropertyValue(name).trim() || fallback;
    const chart = createChart(host, {
      autoSize: true,
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
    setRenderTick((v) => v + 1);
  }, [candles]);
  useEffect(() => {
    const priceFormat = tickSize === null ? null : chartPriceFormat(tickSize);
    if (priceFormat) seriesRef.current?.applyOptions({ priceFormat });
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
  const relative = (event: { clientX: number; clientY: number }) => {
    const r = hostRef.current?.getBoundingClientRect();
    return r ? { x: event.clientX - r.left, y: event.clientY - r.top } : null;
  };
  const targetsPendingLimitLine = (target: EventTarget | null) =>
    target instanceof Element &&
    target.closest("[data-pending-limit-line], [data-active-limit-line], [data-chart-control]") !== null;
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
    visiblePendingLimitDrafts.length > 0 || activeLimitEdit.activeCandidate !== null;
  const deleteSelected = useCallback(() => {
    if (selectedId) {
      commit(drawings.filter((d) => d.id !== selectedId));
      setSelectedId(null);
    }
  }, [commit, drawings, selectedId]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
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
      className="chart-panel workspace-panel"
      aria-label="Candlestick chart"
    >
      <div className="chart-content-row">
        <DrawingToolbar
          activeTool={tool}
          magnet={magnet}
          selected={selectedId !== null}
          onTool={setTool}
          onMagnet={() => setMagnet((v) => !v)}
          onUndo={() => setDrawings(historyRef.current.undo())}
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
        <DrawingOverlay
          drawings={drawings}
          selectedId={selectedId}
          tool={tool}
          magnet={magnet}
          candles={candles}
          coordinates={coordinates}
          onCommit={commit}
          onSelect={setSelectedId}
          onDrawingComplete={() => setTool("select")}
          onDrawingGesture={() => {
            gesture.current = null;
          }}
        />
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
              onPointerDown={(event) => activeLimitEdit.pointerDown(event, order)}
              onPointerMove={activeLimitEdit.pointerMove}
              onPointerUp={activeLimitEdit.pointerUp}
              onPointerCancel={activeLimitEdit.pointerCancel}
              style={{
                top,
                right:
                  chartRef.current?.priceScale("right").width() ||
                  PRICE_SCALE_WIDTH_FALLBACK,
              }}
            >
              <span>{displayedPrice}</span>
              {editing && (activeLimitEdit.state.mode === "PENDING_CONFIRM" || activeLimitEdit.state.mode === "AMENDING" || activeLimitEdit.state.mode === "CANCELLING") ? (
                <div className="active-limit-actions">
                  <TradingControlButton className="active-limit-confirm" aria-label={`Confirm amend ${order.order_id}`} onTap={() => void activeLimitEdit.confirm()} disabled={activeLimitEdit.state.mode !== "PENDING_CONFIRM"}>✓</TradingControlButton>
                  <TradingControlButton className="active-limit-dismiss" aria-label={`Cancel Limit ${order.order_id}`} onTap={() => void activeLimitEdit.cancel().catch(() => {})} disabled={activeLimitEdit.state.mode !== "PENDING_CONFIRM"}>×</TradingControlButton>
                </div>
              ) : null}
              {activeCancelVisible ? (
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
              confirmDisabled={
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
                    const draftIds = visiblePendingLimitDrafts.map((draft) => draft.draftId);
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
                    const draftIds = visiblePendingLimitDrafts.map((draft) => draft.draftId);
                    const activeCandidate = activeLimitEdit.activeCandidate;
                    setDismissAllPendingOpen(false);
                    void cancelVisibleLimitCandidates({
                      draftIds,
                      activeCandidate,
                      dismissDrafts: () => onPendingLimitDismissAll?.(),
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
              setSelectedId(null);
              setClearConfirmationOpen(false);
            }}
          />
        ) : null}
      </div>
      </div>
    </section>
  );
}
