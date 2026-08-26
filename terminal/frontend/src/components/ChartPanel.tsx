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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  type DrawingCoordinates,
  DrawingOverlay,
} from "../chart/DrawingOverlay";
import { DrawingToolbar } from "../chart/DrawingToolbar";
import {
  DrawingHistory,
  type DrawingObject,
  type DrawingTool,
  deserializeDrawings,
  serializeDrawings,
} from "../chart/drawingModel";
import { isAtLatest } from "../chart/followLatest";
import {
  calculateDirectionalPinch,
  scaleRangeAroundAnchor,
} from "../chart/gestureMath";
import type { Candle } from "../contracts/marketData";

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
      startLogical: number;
      xRange: LogicalRange;
    }
  | null;

export function ChartPanel({
  candles,
  symbol = "BTCUSDT",
  timeframe = "5m",
}: {
  candles: readonly Candle[];
  symbol?: string;
  timeframe?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null),
    chartRef = useRef<IChartApi | null>(null),
    seriesRef = useRef<Series | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>()),
    gesture = useRef<Gesture>(null);
  const candleCountRef = useRef(candles.length);
  const followLatestRef = useRef(true);
  candleCountRef.current = candles.length;
  const [manualPrice, setManualPrice] = useState(false),
    [followLatest, setFollowLatest] = useState(true),
    [renderTick, setRenderTick] = useState(0),
    [tool, setTool] = useState<DrawingTool>("select"),
    [magnet, setMagnet] = useState(false),
    [selectedId, setSelectedId] = useState<string | null>(null);
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
    setFollowLatest(next);
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
      },
      timeScale: {
        visible: true,
        borderColor: "#303b47",
        timeVisible: true,
        rightOffset: 3,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
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
    const listener = (range: LogicalRange | null) => {
      setRenderTick((v) => v + 1);
      applyFollowLatest(isAtLatest(range, candleCountRef.current));
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(listener);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(listener);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [applyFollowLatest]);
  useEffect(() => {
    seriesRef.current?.setData(
      candles.map((c, i) => ({
        time: candleTime(c, i),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );
    if (followLatestRef.current)
      chartRef.current?.timeScale().scrollToPosition(0, false);
    setRenderTick((v) => v + 1);
  }, [candles]);
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
  const onPointerDown = (event: React.PointerEvent) => {
    if (event.target instanceof Element && event.target.closest(".snap-latest"))
      return;
    const p = relative(event);
    if (!p) return;
    pointers.current.set(event.pointerId, p);
    event.currentTarget.setPointerCapture(event.pointerId);
    if (pointers.current.size === 2) {
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
      const logical = chart.timeScale().coordinateToLogical(p.x);
      if (logical !== null)
        gesture.current = {
          type: "plot-pan",
          id: event.pointerId,
          startLogical: logical,
          xRange: xr,
        };
    }
  };
  const onPointerMove = (event: React.PointerEvent) => {
    if (!pointers.current.has(event.pointerId)) return;
    const p = relative(event),
      chart = chartRef.current;
    if (!p || !chart) return;
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
      if (d.axes === "X" || d.axes === "XY")
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
        setManualPrice(true);
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
      setManualPrice(true);
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
      const logical = chart.timeScale().coordinateToLogical(p.x);
      if (logical === null) return;
      const delta = g.startLogical - logical;
      chart.timeScale().setVisibleLogicalRange({
        from: g.xRange.from + delta,
        to: g.xRange.to + delta,
      });
      applyFollowLatest(false);
      event.preventDefault();
    }
  };
  const endPointer = (event: React.PointerEvent) => {
    pointers.current.delete(event.pointerId);
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
        setManualPrice(true);
      }
    }
    event.preventDefault();
  };
  const resetAuto = () => {
      chartRef.current?.priceScale("right").setAutoScale(true);
      setManualPrice(false);
    },
    snapLatest = () => {
      const timeScale = chartRef.current?.timeScale();
      if (!timeScale) return;
      timeScale.scrollToRealTime();
    };
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
      <header className="panel-header">
        <div>
          <span>Chart · {timeframe}</span>
          <small>{manualPrice ? "Manual price" : "Auto price"}</small>
        </div>
      </header>
      <div
        className="chart-stage"
        role="application"
        aria-label="Interactive market chart"
        onPointerDownCapture={onPointerDown}
        onPointerMoveCapture={onPointerMove}
        onPointerUpCapture={endPointer}
        onPointerCancelCapture={endPointer}
        onLostPointerCapture={endPointer}
        onWheel={onWheel}
        onDoubleClick={(e) => {
          const p = relative(e);
          if (
            p &&
            p.x >
              (hostRef.current?.clientWidth ?? 0) -
                (chartRef.current?.priceScale("right").width() ||
                  PRICE_SCALE_WIDTH_FALLBACK)
          )
            resetAuto();
        }}
      >
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
          onDrawingGesture={() => {
            gesture.current = null;
          }}
        />
        <DrawingToolbar
          activeTool={tool}
          magnet={magnet}
          selected={selectedId !== null}
          onTool={setTool}
          onMagnet={() => setMagnet((v) => !v)}
          onDelete={deleteSelected}
          onUndo={() => setDrawings(historyRef.current.undo())}
          onRedo={() => setDrawings(historyRef.current.redo())}
          onLock={() =>
            commit(
              drawings.map((d) =>
                d.id === selectedId ? { ...d, locked: !d.locked } : d,
              ),
            )
          }
          onClear={() => {
            if (
              drawings.length &&
              confirm("Clear all drawings for this symbol and timeframe?")
            ) {
              commit([]);
              setSelectedId(null);
            }
          }}
        />
        {!followLatest && (
          <button
            className="snap-latest"
            type="button"
            aria-label="Snap to latest candle"
            onClick={snapLatest}
          >
            →|
          </button>
        )}
        {manualPrice && (
          <button
            className="auto-price-reset"
            type="button"
            aria-label="Reset automatic price scale"
            onClick={resetAuto}
          >
            Auto
          </button>
        )}
      </div>
    </section>
  );
}
