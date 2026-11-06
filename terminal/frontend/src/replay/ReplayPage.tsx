import {
  CandlestickSeries, ColorType, CrosshairMode, LineSeries, LineStyle, createChart,
  type IChartApi, type ISeriesApi, type Logical, type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  completeHourlyCandles, parseReplayDocument, syntheticReplay, simulationActionJournal, visibleReplay, visibleGeometry, visibleGeometryHistory, visibleEarlyGeometry, visiblePriorLevels, visiblePriorBreaks, visibleDmi, visibleObservations,
  visibleH017BlueRiskPreviews, studyH017BlueCandidates, visibleH017CandidateStudy,
  type ReplayDocument, type ReplayEvent,
} from "./replayModel";
import { visibleExecutionMarkers, TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR } from "./executionMarkers";
import { rayEndPoint } from "../chart/drawingGeometry";
import { DrawingOverlay } from "../chart/DrawingOverlay";
import type { DrawingObject, DrawingTool } from "../chart/drawingModel";
import { chartLogicalAtTime, drawingLogicalToTime, timeAtChartLogical, timeToDrawingLogical } from "./replayDrawingCoordinates";
import "./replay.css";

function label(event: ReplayEvent): string {
  switch (event.kind) {
    case "CANDLE_CLOSED": return "Свеча закрылась";
    case "ENTRY_SIGNAL": return "Сигнал " + (event.side ?? "");
    case "ENTRY_FILLED": return "Вход " + (event.side ?? "");
    case "EXIT_FILLED": return "Выход " + (event.reason ?? "");
  }
}
// The replay tools share the terminal's compact icon-first interaction, with
// real vector pictograms rather than font-dependent textual approximations.
const REPLAY_DRAWING_TOOLS: Array<{ tool: DrawingTool; label: string }> = [
  { tool: "crosshair", label: "Курсор / сдвиг" },
  { tool: "select", label: "Редактировать" },
  { tool: "trend", label: "Трендовая" },
  { tool: "horizontal", label: "Горизонталь" },
  { tool: "ray", label: "Луч" },
  { tool: "horizontal-ray", label: "Горизонтальный луч" },
  { tool: "vertical", label: "Вертикаль" },
  { tool: "fibonacci", label: "Fibonacci" },
  { tool: "ruler", label: "Линейка" },
  { tool: "rectangle", label: "Прямоугольник" },
];
const REPLAY_TOOL_PATHS: Record<DrawingTool | "delete", string> = {
  crosshair: "M12 2v20M2 12h20M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6",
  select: "M4 3l5 17 3.4-6.6L19 10z",
  trend: "M4 20L20 4M4 17v3h3M17 4h3v3",
  horizontal: "M3 12h18M3 9v6M21 9v6",
  ray: "M3 20L20 3M14 3h6v6",
  "horizontal-ray": "M3 12h18M15 6l6 6-6 6",
  vertical: "M12 3v18M9 3h6M9 21h6",
  fibonacci: "M4 3v18M3 18h18M5 14h16M7 10h14M10 6h11",
  ruler: "M4 19L19 4l2 2L6 21zM10 14l-2-2M13 11l-2-2M16 8l-2-2",
  rectangle: "M4 5h16v14H4zM4 9v2M20 13v2",
  delete: "M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13M10 10v7M14 10v7",
};
function ReplayToolIcon({ tool }: { tool: DrawingTool | "delete" }) {
  return <svg className="replay-tool-icon" viewBox="0 0 24 24"
    data-tool-icon={tool} aria-hidden="true" focusable="false">
    <path d={REPLAY_TOOL_PATHS[tool]} />
  </svg>;
}
function ReplayChart({ document, cursor, showDebug, timeframe, drawings, selectedId,
  drawingTool, onDrawingsChange, onSelectDrawing, onDrawingGesture }: {
  document: ReplayDocument; cursor: number; showDebug: boolean; timeframe: "5m" | "1h";
  drawings: DrawingObject[]; selectedId: string | null; drawingTool: DrawingTool;
  onDrawingsChange: (next: DrawingObject[]) => void;
  onSelectDrawing: (id: string | null) => void;
  onDrawingGesture: () => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const executionCanvas = useRef<HTMLCanvasElement>(null);
  const [drawingViewport, setDrawingViewport] = useState(0);
  const [pricePaneHeight, setPricePaneHeight] = useState(0);
  const renderExecutions = useRef<() => void>(() => {});
   const indicators = useRef<Record<"PLUS" | "MINUS" | "ADX" | "LEVEL", ISeriesApi<"Line">> | null>(null);
  const shown = useMemo(() => visibleReplay(document.events, cursor), [document, cursor]);
  const displayCandles = useMemo(() => timeframe === "1h"
    ? completeHourlyCandles(shown.candles) : shown.candles, [shown.candles, timeframe]);
  const earlyGeometry = useMemo(
    () => visibleEarlyGeometry(document, shown.lastTimeMs),
    [document, shown.lastTimeMs],
  );
  const observedDmi = useMemo(() => visibleDmi(document, shown.candles.length), [document, shown.candles.length]);
  // Only the final 5m DMI reading of each completed H1 is plotted on the H1 axis.
  const indicatorSamples = timeframe === "1h"
    ? displayCandles.map(hour => {
      const index = shown.candles.findIndex(bar => bar.end_ms === hour.end_ms);
      return index >= 0 ? observedDmi[index] : undefined;
    })
    : observedDmi;
  const observedTouches = useMemo(() => visibleObservations(document, shown.lastTimeMs), [document, shown.lastTimeMs]);
  const blueRiskPreviews = useMemo(
    () => visibleH017BlueRiskPreviews(document, shown.lastTimeMs),
    [document, shown.lastTimeMs],
  );
  const priorBreaks = useMemo(
    () => visiblePriorBreaks(document, shown.lastTimeMs),
    [document, shown.lastTimeMs],
  );
  const latestDmi = observedDmi.at(-1);
  const dmiValue = (value: number | null | undefined) => value == null ? "—" : value.toFixed(1);

  useEffect(() => {
    if (!container.current) return;
    const api = createChart(container.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#121923" }, textColor: "#bcc8d8" },
      grid: { vertLines: { color: "#202d3d" }, horzLines: { color: "#202d3d" } },
      timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 42 },
      // Free crosshair movement: no magnet snapping to candle body or wick extrema.
      crosshair: { mode: CrosshairMode.Normal },
    });
    const candles = api.addSeries(CandlestickSeries, {
      upColor: "#2fc596", downColor: "#ed6978", wickUpColor: "#2fc596",
      wickDownColor: "#ed6978", borderVisible: false,
    });
     // Lightweight Charts v5: a second pane shares the exact candle time axis
    // and crosshair. Unlike an overlay, ADX uses its own 0..100 value scale.
    const paneOptions = {
      lineWidth: 1 as const, priceLineVisible: false, lastValueVisible: false,
      crosshairMarkerVisible: false, title: "",
      priceFormat: { type: "price" as const, precision: 1, minMove: 0.1 },
    };
    const indicatorLines = {
      PLUS: api.addSeries(LineSeries, { ...paneOptions, color: "#25c776" }, 1),
      MINUS: api.addSeries(LineSeries, { ...paneOptions, color: "#f16a72" }, 1),
      ADX: api.addSeries(LineSeries, { ...paneOptions, color: "#60a5fa" }, 1),
      LEVEL: api.addSeries(LineSeries, {
        ...paneOptions, color: "#8595ab", lineWidth: 1,
        lineStyle: LineStyle.Dashed,
      }, 1),
    };
    api.panes()[1]?.setHeight(185);
    indicators.current = indicatorLines;
    chart.current = api;
    series.current = candles;
    // Repaint true-price execution triangles when chart scroll/zoom/resize moves.
    const refresh = () => renderExecutions.current();
    const refreshViewport = () => {
      refresh();
      const nextHeight = api.panes()[0]?.getHeight() ?? 0;
      setPricePaneHeight(current => current === nextHeight ? current : nextHeight);
      setDrawingViewport(current => current + 1);
    };
    api.timeScale().subscribeVisibleLogicalRangeChange(refreshViewport);
    api.subscribeCrosshairMove(refresh);
    const resize = new ResizeObserver(refreshViewport);
    resize.observe(container.current);
    refreshViewport();
    return () => {
      resize.disconnect();
      api.unsubscribeCrosshairMove(refresh);
      api.timeScale().unsubscribeVisibleLogicalRangeChange(refreshViewport);
      chart.current = null;
      series.current = null;
       indicators.current = null;
      api.remove();
    };
  }, []);

  useEffect(() => {
    const candleSeries = series.current;
    if (!candleSeries) return;
    candleSeries.setData(displayCandles.map((c) => ({
      time: (c.start_ms / 1000) as UTCTimestamp,
      open: c.open, high: c.high, low: c.low, close: c.close,
    })));
     const dmiSeries = indicators.current;
    if (dmiSeries) {
      const linePoints = (key: "plus_di" | "minus_di" | "adx") => {
        const values: { time: UTCTimestamp; value: number }[] = [];
        indicatorSamples.forEach((sample, index) => {
          const value = sample?.[key];
          if (value != null) {
            values.push({
              // Chart bar's X is its START, while the sample becomes known
              // only at the CLOSE. We reveal it only after that close event.
              time: (displayCandles[index].start_ms / 1000) as UTCTimestamp,
              value,
            });
          }
        });
        return values;
      };
      dmiSeries.PLUS.setData(linePoints("plus_di"));
      dmiSeries.MINUS.setData(linePoints("minus_di"));
      dmiSeries.ADX.setData(linePoints("adx"));
      const first = displayCandles[0];
      const last = displayCandles.at(-1);
      dmiSeries.LEVEL.setData(first && last ? [
        { time: (first.start_ms / 1000) as UTCTimestamp, value: 20 },
        ...(last.start_ms !== first.start_ms
          ? [{ time: (last.start_ms / 1000) as UTCTimestamp, value: 20 }]
          : []),
      ] : []);
    }
     // Match robot_position_chart.py's true-price filled triangles, not
    // Lightweight Charts' aboveBar/belowBar markers (which shift the Y).
    // The overlay is visual only, no API/Robot/PAPER connection.
    renderExecutions.current = () => {
      const canvas = executionCanvas.current;
      const api = chart.current;
      if (!canvas || !api) return;
      const ratio = window.devicePixelRatio || 1;
      const bounds = canvas.getBoundingClientRect();
      const width = bounds.width, height = bounds.height;
      if (canvas.width !== Math.round(width * ratio) ||
          canvas.height !== Math.round(height * ratio)) {
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
      }
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const paneHeight = api.panes()[0]?.getHeight() ?? height;
      const priceWidth = Math.min(width, api.timeScale().width());
      context.save();
      context.beginPath();
      context.rect(0, 0, priceWidth, paneHeight);
      context.clip();

      // Reuse the terminal's existing two-anchor ray projection. Source
      // anchors/time of knowledge come from the frozen causal geometry feed;
      // DrawingOverlay's rayEndPoint extends the line to the price pane edge.
      // Never refit the line to the replayed price candles.
      const knownLines = visibleGeometry(document, shown.lastTimeMs);
      const historicalLines = visibleGeometryHistory(document, shown.lastTimeMs);
      // Three-pivot wick guides are visual research previews, not confirmed
      // four-pivot H1 trends. They never mutate archived trading/geometry.
      const drawableLines = [...historicalLines, ...earlyGeometry];
      const knownPriors = visiblePriorLevels(document, shown.lastTimeMs);
      const brokenByVersion = new Map(priorBreaks.map(item => [item.trend_version, item]));
      let paintedGeometry = 0;
      for (const line of drawableLines) {
        // Line anchors can predate the requested playback window. Lightweight
        // Charts returns null for timestamps not present in loaded candles.
        // Project the original, frozen two-point slope (CausalLine.value_at)
        // onto two actual VISIBLE candle times, without any new fitting.
        const startingBar = displayCandles.find(bar => bar.start_ms >= line.from_ms);
        // An improved pivot/slope is NOT a break. Keep the former solid
        // version visible until the same movement's verified cancellation.
        const retiredAt = line.retired_at_ms;
        const endingBar = retiredAt !== undefined
          ? displayCandles.slice().reverse().find(bar => bar.start_ms < retiredAt)
          : displayCandles.at(-1);
        if (!startingBar || !endingBar || startingBar.start_ms >= endingBar.start_ms) continue;
        const priceAt = (at_ms: number) => line.from_price +
          (line.to_price - line.from_price) * (at_ms - line.from_ms) / (line.to_ms - line.from_ms);
        const x1 = api.timeScale().timeToCoordinate((startingBar.start_ms / 1000) as UTCTimestamp);
        const x2 = api.timeScale().timeToCoordinate((endingBar.start_ms / 1000) as UTCTimestamp);
        const y1 = candleSeries.priceToCoordinate(priceAt(startingBar.start_ms));
        const y2 = candleSeries.priceToCoordinate(priceAt(endingBar.start_ms));
        if (x1 === null || x2 === null || y1 === null || y2 === null) continue;
        // Only a confirmed retirement ends the line. Add a short VISUAL
        // tail beyond that point; no arbitrary candle-based strategy rule.
        const tailPx = retiredAt === undefined ? 0 : Math.max(0, Math.min(8, priceWidth - x2));
        const end = retiredAt !== undefined
          ? { x: x2 + tailPx, y: y2 + (x2 > x1 ? (y2 - y1) * tailPx / (x2 - x1) : 0) }
          : rayEndPoint(
              { x: x1, y: y1 }, { x: x2, y: y2 },
              { width: priceWidth, height: paneHeight },
            );
        context.beginPath();
        // Main H1 and reference M5 stay solid and fully opaque in the archive.
        // Dashed yellow exclusively identifies a TARGET_1H line.
        context.strokeStyle = line.kind === "REFERENCE_5M" ? "#57aaff" : "#f6dc59";
        context.lineWidth = 1;
        context.setLineDash(line.kind === "TARGET_1H" ? [6, 4] : []);
        context.moveTo(x1, y1);
        context.lineTo(end.x, end.y);
        context.stroke();
        paintedGeometry += 1;
      }
      context.setLineDash([]);
      // Purple prior: second confirmed touch of the H1 main line, at its wick.
      // Old levels stop at the time of replacement; only the latest level
      // extends into the right-hand whitespace. No future version is shown.
      let paintedPriors = 0;
      for (const prior of knownPriors) {
        const startingBar = displayCandles.find(bar => bar.start_ms >= prior.at_ms);
        if (!startingBar) continue;
        const x1 = api.timeScale().timeToCoordinate((startingBar.start_ms / 1000) as UTCTimestamp);
        const y = candleSeries.priceToCoordinate(prior.price);
        const matchingBreak = brokenByVersion.get(prior.trend_version);
        const stoppedAt = Math.min(
          prior.superseded_at_ms ?? Infinity,
          matchingBreak?.confirmed_at_ms ?? Infinity,
        );
        const historical = Number.isFinite(stoppedAt);
        const x2 = historical
          ? api.timeScale().timeToCoordinate((
              (displayCandles.slice().reverse().find(bar => bar.start_ms < stoppedAt)?.start_ms ?? -1) / 1000
            ) as UTCTimestamp)
          : priceWidth;
        if (x1 === null || y === null || x2 === null || x2 <= x1) continue;
        context.beginPath();
        context.lineWidth = 1;
        context.strokeStyle = historical ? "rgba(177, 123, 239, 0.65)" : "#b17bef";
        context.setLineDash(historical ? [3, 4] : []);
        context.moveTo(x1, y);
        context.lineTo(x2, y);
        context.stroke();
        paintedPriors += 1;
      }
      context.setLineDash([]);
      // Hollow marks are geometry observations, never entry/fill triangles.
      let paintedObservations = 0;
      for (const item of (showDebug ? observedTouches : [])) {
        const x = api.timeScale().timeToCoordinate(((item.time_ms - 300_000) / 1000) as UTCTimestamp);
        const y = candleSeries.priceToCoordinate(
          item.kind === "MAIN_1H_TOUCH" ? item.line_price : item.price,
        );
        if (x === null || y === null || x < 0 || x > priceWidth || y < 0 || y > paneHeight) continue;
        context.beginPath();
        context.strokeStyle = item.kind === "MAIN_1H_TOUCH" ? "#f6dc59" : "#80caff";
        context.lineWidth = 1.5;
        if (item.kind === "MAIN_1H_TOUCH") {
          context.arc(x, y, 4, 0, Math.PI * 2);
        } else {
          context.moveTo(x, y - 5); context.lineTo(x + 5, y);
          context.lineTo(x, y + 5); context.lineTo(x - 5, y);
          context.closePath();
        }
        context.stroke();
        paintedObservations += 1;
      }
      // Hollow squares are H-017 blue-line risk previews, never fills.
      let paintedBlueRisk = 0;
      for (const item of (showDebug ? blueRiskPreviews : [])) {
        const x = api.timeScale().timeToCoordinate((item.open_ms / 1000) as UTCTimestamp);
        const y = candleSeries.priceToCoordinate(item.entry_price);
        if (x === null || y === null || x < 0 || x > priceWidth || y < 0 || y > paneHeight) continue;
        context.beginPath();
        context.strokeStyle = item.risk_status === "RISK_PASS" ? "#25c776" : "#f1a46a";
        context.lineWidth = 1.5;
        context.rect(x - 4, y - 4, 8, 8);
        context.stroke();
        paintedBlueRisk++;
      }
      const fills = visibleExecutionMarkers(document.events.slice(0, cursor), shown.candles);
      let rendered = 0;
      for (const fill of fills) {
        const stamp = timeframe === "1h"
          ? Math.floor(fill.candle_start_ms / 3_600_000) * 3_600_000
          : fill.candle_start_ms;
        if (!displayCandles.some(bar => bar.start_ms === stamp)) continue;
        const x = api.timeScale().timeToCoordinate((stamp / 1000) as UTCTimestamp);
        const y = candleSeries.priceToCoordinate(fill.price);
        if (x === null || y === null || !Number.isFinite(x) || !Number.isFinite(y)
            || x < -7 || x > width + 7 || y < -7 || y > paneHeight + 7) {
          continue; // Never move an off-screen fill to a fictitious price.
        }
        context.beginPath();
        if (fill.side === "Buy") {
          context.moveTo(x, y - 7);
          context.lineTo(x - 7, y + 6);
          context.lineTo(x + 7, y + 6);
        } else {
          context.moveTo(x, y + 7);
          context.lineTo(x - 7, y - 6);
          context.lineTo(x + 7, y - 6);
        }
        context.closePath();
        context.fillStyle = fill.side === "Buy" ? TELEGRAM_BUY_COLOR : TELEGRAM_SELL_COLOR;
        context.fill();
        context.lineWidth = 0.8;
        context.strokeStyle = "#000000";
        context.stroke();
        rendered += 1;
      }
      context.restore();
      canvas.dataset.visibleFills = String(rendered);
      canvas.dataset.visibleGeometry = String(knownLines.length);
      canvas.dataset.visibleEarlyGeometry = String(earlyGeometry.length);
      canvas.dataset.visiblePriors = String(knownPriors.length);
      canvas.dataset.paintedPriors = String(paintedPriors);
      canvas.dataset.paintedGeometry = String(paintedGeometry);
      canvas.dataset.visibleObservations = String(paintedObservations);
      canvas.dataset.visibleBlueRisk = String(paintedBlueRisk);
    };
    renderExecutions.current();
    // Chart recalculates pixel coordinates after updating series/timescale.
    const redrawId = requestAnimationFrame(() => renderExecutions.current());
    return () => cancelAnimationFrame(redrawId);
  }, [shown, document, cursor, observedDmi, observedTouches, blueRiskPreviews, priorBreaks, showDebug, timeframe, displayCandles, earlyGeometry]);

  // The editable layer reuses the terminal's drawing tools, but stores its X
  // anchors in absolute UTC M5 slots rather than indices of the selected TF.
  // Both charts merely project that immutable timestamp; neither edits H-017.
  const drawingCoordinates = {
    logicalToX: (value: number) => {
      const logical = chartLogicalAtTime(drawingLogicalToTime(value), displayCandles);
      return logical === null ? null :
        chart.current?.timeScale().logicalToCoordinate(logical as Logical) ?? null;
    },
    xToLogical: (x: number) => {
      const logical = chart.current?.timeScale().coordinateToLogical(x);
      if (logical == null) return null;
      const time = timeAtChartLogical(logical, displayCandles);
      return time === null ? null : timeToDrawingLogical(time);
    },
    priceToY: (price: number) => series.current?.priceToCoordinate(price) ?? null,
    yToPrice: (y: number) => series.current?.coordinateToPrice(y) ?? null,
  };
  return (
    <div className="replay-chart-shell" data-chart-timeframe={timeframe}
      data-displayed-candles={displayCandles.length} data-drawing-viewport={drawingViewport}>
      <div className="replay-chart-frame">
        <div className="replay-chart" ref={container}
          aria-label="Свечной график и нижняя панель ADX DMI" />
        <canvas ref={executionCanvas} className="replay-execution-overlay"
          aria-hidden="true" data-visible-fills="0" data-visible-observations="0" data-visible-blue-risk="0" />
        {pricePaneHeight > 0 && displayCandles.length > 0 &&
          <div className={`replay-drawing-layer tool-${drawingTool}`} style={{ height: pricePaneHeight }}
            data-drawing-count={drawings.length}>
            <DrawingOverlay drawings={drawings} selectedId={selectedId} tool={drawingTool}
              magnet={false} candles={[]} coordinates={drawingCoordinates}
              onCommit={onDrawingsChange} onSelect={onSelectDrawing}
              onDrawingGesture={onDrawingGesture} onDrawingComplete={() => {}} />
          </div>}
      </div>
      <div className="replay-dmi-legend" role="group" aria-label="Индикатор ADX DMI">
        <strong>ADX/DMI {document.dmi_5m
          ? `(${document.dmi_5m.di_length}, ${document.dmi_5m.adx_smoothing})`
          : "(14, 14)"} · 5м</strong>
        <span className="replay-dmi-plus">+DI {dmiValue(latestDmi?.plus_di)}</span>
        <span className="replay-dmi-minus">−DI {dmiValue(latestDmi?.minus_di)}</span>
        <span className="replay-dmi-adx">ADX {dmiValue(latestDmi?.adx)}</span>
        <span className="replay-dmi-level">Уровень 20</span>
        {document.mode === "MARKET_ONLY" && !document.dmi_5m &&
          <span>Старый архив: расчёт ADX отсутствует</span>}
        {document.dmi_5m && latestDmi?.adx == null &&
          <span>Прогрев ADX: 28 закрытых свечей</span>}
      </div>
    </div>
  );
}

function utcDayOffset(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 86_400_000).toISOString().slice(0, 10);
}

export function ReplayPage() {
  const [document, setDocument] = useState<ReplayDocument>(() => syntheticReplay());
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [startDate, setStartDate] = useState(() => utcDayOffset(3));
  const [endDate, setEndDate] = useState(() => utcDayOffset(1));
  const [historyLoading, setHistoryLoading] = useState(false);
  const historyRequest = useRef<AbortController | null>(null);
  const bundledRequest = useRef<AbortController | null>(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(8);
  const [showDebug, setShowDebug] = useState(false);
  const [timeframe, setTimeframe] = useState<"5m" | "1h">("5m");
  const [drawingTool, setDrawingTool] = useState<DrawingTool>("crosshair");
  const [drawings, setDrawings] = useState<DrawingObject[]>([]);
  const [selectedDrawing, setSelectedDrawing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileLabel, setFileLabel] = useState("Синтетический пример");
  const shown = useMemo(() => visibleReplay(document.events, cursor), [document, cursor]);
  const total = document.events.length;
  const progress = Math.round(100 * cursor / total);
  const priorBreaks = useMemo(
    () => visiblePriorBreaks(document, shown.lastTimeMs),
    [document, shown.lastTimeMs],
  );
  const latestPriorBreak = priorBreaks.at(-1);
  const publishedGeometry = useMemo(
    () => visibleGeometry(document, shown.lastTimeMs),
    [document, shown.lastTimeMs],
  );
  const earlyGeometry = useMemo(
    () => visibleEarlyGeometry(document, shown.lastTimeMs),
    [document, shown.lastTimeMs],
  );
  const earlyMain = earlyGeometry.find(line => line.kind === "MAIN_1H");
  const earlyBlueCount = earlyGeometry.filter(line => line.kind === "REFERENCE_5M").length;
  const activeMain = publishedGeometry.find(line => line.kind === "MAIN_1H");
  const latestPrior = useMemo(
    () => visiblePriorLevels(document, shown.lastTimeMs).at(-1),
    [document, shown.lastTimeMs],
  );
  const oppositeMainConfirmed = latestPriorBreak !== undefined &&
    activeMain?.side === latestPriorBreak.new_side &&
    activeMain.available_at_ms >= latestPriorBreak.confirmed_at_ms;
  const priorAlreadyBroken = latestPrior !== undefined && priorBreaks.some(event =>
    event.previous_side === latestPrior.side &&
    event.prior_at_ms === latestPrior.at_ms &&
    event.prior_price === latestPrior.price &&
    event.trend_version === latestPrior.trend_version
  );
  const recentEvents = document.events.slice(Math.max(0, cursor - 8), cursor);
  const recentFromMs = recentEvents[0]?.time_ms ?? Infinity;
  const lastTimeline = [
    ...recentEvents.map(event => ({
      kind: "REPLAY" as const, time_ms: event.time_ms, key: String(event.sequence), event,
    })),
    ...priorBreaks.filter(item => item.confirmed_at_ms >= recentFromMs).map(item => ({
      kind: "PRIOR_BREAK" as const, time_ms: item.confirmed_at_ms,
      key: "prior-" + item.trend_version, breakEvent: item,
    })),
  ].sort((a, b) => b.time_ms - a.time_ms).slice(0, 8);
  const observedTouches = useMemo(() => visibleObservations(document, shown.lastTimeMs), [document, shown.lastTimeMs]);
  const blueRiskPreviews = useMemo(
    () => visibleH017BlueRiskPreviews(document, shown.lastTimeMs),
    [document, shown.lastTimeMs],
  );
  const dmiCrossings = useMemo(
    () => visibleDmi(document, shown.candles.length).flatMap(point => point.crossings ?? []),
    [document, shown.candles.length],
  );
  const retrospectiveStudy = useMemo(() => studyH017BlueCandidates(document), [document]);
  const visibleStudy = useMemo(
    () => visibleH017CandidateStudy(retrospectiveStudy, shown.lastTimeMs),
    [retrospectiveStudy, shown.lastTimeMs],
  );
  const cohorts = (withCross: boolean) => visibleStudy.filter(row =>
    row.crossings_at_open !== null && (row.crossings_at_open.length > 0) === withCross);
  const countTouch = (rows: typeof visibleStudy, kind: typeof visibleStudy[number]["first_touch"]) =>
    rows.filter(row => row.first_touch === kind).length;
  const fileInput = useRef<HTMLInputElement>(null);

  function syncImportedMarketSelection(parsed: ReplayDocument) {
    if (parsed.symbol) setSymbol(parsed.symbol);
    const first = parsed.events.find(item => item.kind === "CANDLE_CLOSED")?.candle;
    const last = parsed.events.filter(item => item.kind === "CANDLE_CLOSED").at(-1)?.candle;
    if (first && last) {
      setStartDate(new Date(first.start_ms).toISOString().slice(0, 10));
      setEndDate(new Date(last.end_ms).toISOString().slice(0, 10));
    }
  }

  // The audited GRASSUSDT archive is optional and read ONLY from loopback.
  // Source check is strict: no private/PAPER runs and no silent fallback on
  // invalid bundled data. Missing bundle (204) retains the standalone demo.
  useEffect(() => {
    const controller = new AbortController();
    bundledRequest.current = controller;
    void (async () => {
      try {
        const response = await fetch("/local-replay/bundled", {
          method: "GET", cache: "no-store", signal: controller.signal,
        });
        if (response.status === 204) return;
        if (!response.ok) throw new Error("Локальная история недоступна");
        const raw = await response.text();
        if (raw.length > 24 * 1024 * 1024) throw new Error("Архив больше 24 МБ");
        const parsed = parseReplayDocument(JSON.parse(raw) as unknown);
        if (parsed.mode !== "MARKET_ONLY" ||
            parsed.market_data_source !== "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M") {
          throw new Error("Неверный тип публичного архива");
        }
        if (controller.signal.aborted) return;
        setDocument(parsed);
        syncImportedMarketSelection(parsed);
        setPlaying(false); setCursor(0);
        setFileLabel("Проверенный публичный архив · GRASSUSDT");
        setError(null);
      } catch (e) {
        if (!controller.signal.aborted) {
          setError("Не удалось загрузить встроенный архив: " +
            (e instanceof Error ? e.message : "ошибка JSON"));
        }
      } finally {
        if (bundledRequest.current === controller) bundledRequest.current = null;
      }
    })();
    return () => {
      controller.abort();
      if (bundledRequest.current === controller) bundledRequest.current = null;
    };
  }, []);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setCursor((current) => Math.min(total, current + 1));
    }, Math.max(16, Math.floor(1000 / rate)));
    return () => window.clearInterval(timer);
  }, [playing, rate, total]);

  useEffect(() => {
    if (cursor >= total) setPlaying(false);
  }, [cursor, total]);

  async function loadFile(file?: File) {
    if (!file) return;
    bundledRequest.current?.abort(); bundledRequest.current = null;
    historyRequest.current?.abort();
    historyRequest.current = null;
    setHistoryLoading(false);
    setPlaying(false);
    try {
      if (file.size > 24 * 1024 * 1024) throw new Error("Файл больше 24 МБ");
      const data: unknown = JSON.parse(await file.text());
      const parsed = parseReplayDocument(data);
      setDocument(parsed);
      // Manual import also replaces the market selection, never leave stale
      // BTC/date controls beside an imported GRASSUSDT archive.
      if (parsed.mode === "MARKET_ONLY") syncImportedMarketSelection(parsed);
      setDrawings([]); setSelectedDrawing(null); setDrawingTool("crosshair");
      setCursor(0);
      setFileLabel(file.name);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось прочитать файл");
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function loadLocalHistory() {
    bundledRequest.current?.abort(); bundledRequest.current = null;
    historyRequest.current?.abort();
    const controller = new AbortController();
    historyRequest.current = controller;
    setHistoryLoading(true);
    setPlaying(false);
    setError(null);
    try {
      const query = new URLSearchParams({ symbol: symbol.trim().toUpperCase(), start: startDate, end: endDate });
      // Only the loopback Python viewer implements this research-only GET.
      // Never call /api: Vite's /api proxy belongs to the main PAPER backend.
      const response = await fetch("/local-replay/history?" + query.toString(), {
        method: "GET", cache: "no-store", signal: controller.signal,
      });
      const raw: unknown = await response.json();
      if (!response.ok) {
        const reason = typeof raw === "object" && raw !== null && "error" in raw &&
          typeof raw.error === "string" ? raw.error : "История недоступна";
        throw new Error(reason);
      }
      const imported = parseReplayDocument(raw);
      if (imported.mode !== "MARKET_ONLY") throw new Error("История не соответствует режиму MARKET_ONLY");
      if (historyRequest.current !== controller) return;
      setDocument(imported);
      setDrawings([]); setSelectedDrawing(null); setDrawingTool("crosshair");
      setCursor(0);
      setFileLabel("Bybit · публичные свечи · без сделок");
    } catch (e) {
      if (historyRequest.current !== controller) return;
      setError(e instanceof Error ? e.message : "Не удалось загрузить историю");
    } finally {
      if (historyRequest.current === controller) {
        setHistoryLoading(false);
        historyRequest.current = null;
      }
    }
  }

  return (
    <main className="replay-shell">
      <header className="replay-header">
        <div>
          <h1>Машина времени</h1>
        </div>
        <span className="replay-badge">SIMULATION ONLY</span>
      </header>

      <section className="replay-history-controls" aria-label="Публичная история Bybit">
        <label>Инструмент <input aria-label="Инструмент" value={symbol} maxLength={30}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())} /></label>
        <label>С UTC <input aria-label="С UTC" type="date" value={startDate}
          onChange={(e) => setStartDate(e.target.value)} /></label>
        <label>По UTC (не включительно) <input aria-label="По UTC" type="date" value={endDate}
          onChange={(e) => setEndDate(e.target.value)} /></label>
        <button type="button" onClick={() => void loadLocalHistory()} disabled={historyLoading}>
          {historyLoading ? "Загружаю историю…" : "Загрузить Bybit (без сделок)"}
        </button>
      </section>
      <section className="replay-controls" aria-label="Управление воспроизведением">
        <label className="replay-file">
          Загрузить JSON прогона
          <input ref={fileInput} type="file" accept=".json,application/json"
            onChange={(e) => void loadFile(e.target.files?.[0])} />
        </label>
        <button type="button" onClick={() => {
          bundledRequest.current?.abort(); bundledRequest.current = null;
          historyRequest.current?.abort(); historyRequest.current = null;
          setHistoryLoading(false); setPlaying(false); setCursor(0); setError(null);
          setDocument(syntheticReplay()); setFileLabel("Синтетический пример");
          setDrawings([]); setSelectedDrawing(null); setDrawingTool("crosshair");
        }}>Пример</button>
        <button type="button" aria-label="Скачать журнал SIMULATION JSON" onClick={() => {
          const report = simulationActionJournal(document);
          const blob = new Blob([JSON.stringify(report, null, 2) + "\n"], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const anchor = window.document.createElement("a");
          anchor.href = url;
          anchor.download = "simulation-actions.json";
          window.document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
          // Browser owns this temporary object URL; no trade/network request.
          window.setTimeout(() => URL.revokeObjectURL(url), 0);
        }}>Журнал JSON ({simulationActionJournal(document).actions.length})</button>

      </section>

      {error && <p role="alert" className="replay-error">{error}</p>}
      <section className="replay-meta" aria-label="Состояние симулятора">
        <div><span>Источник</span><strong>{fileLabel}</strong></div>
        <div><span>Прогон / рынок</span><strong>{document.simulation_run_id}{document.symbol ? " · " + document.symbol + " · 5m" : ""}</strong></div>
        <div><span>Время рынка</span><strong>{shown.lastTimeMs === null ? "До первого события" :
          new Date(shown.lastTimeMs).toLocaleString("ru-RU", { timeZone: "UTC" }) + " UTC"}</strong></div>
        <div><span>Свечи / входы / выходы</span>
          <strong>{shown.candles.length} / {shown.fills.length} / {shown.exits.length}</strong></div>
      </section>
      <div className="replay-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={progress} aria-label="Прогресс воспроизведения">
        <div style={{ width: progress + "%" }} />
      </div>
      {document.mode === "MARKET_ONLY" && <p className="replay-note">
        РЕАЛЬНЫЕ СВЕЧИ BYBIT · БЕЗ СДЕЛОК:
        {" "}{document.market_data_source === "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M"
          ? "исторические сделки из официального публичного архива, агрегированные в закрытые 5m OHLCV"
          : "публичные свечи API Bybit"}
        {" "}· жёлтые 1H и синие 5m линии — предварительные кандидаты из подтверждённых экстремумов, не проверенная стратегия.
      </p>}
      <details className="replay-diagnostics">
        <summary>Диагностика</summary>
        <label><input type="checkbox" checked={showDebug} onChange={(e) => setShowDebug(e.target.checked)} /> Показать опорные маркеры</label>
      {document.mode === "MARKET_ONLY" && cursor > 0 && <p className="replay-geometry-note"
        role="status" aria-label="Статус трендовой геометрии">
        {publishedGeometry.length
          ? "Геометрия: полная подтверждённая часовая пара 1–3 / 2–4; ранние синие M5-линии сохраняются в истории."
          : earlyMain
            ? `Геометрия: показана предварительная жёлтая H1 по трём подтверждённым экстремумам; полной пары 1–3 / 2–4 ещё нет. Ранних синих M5: ${earlyBlueCount}.`
            : "Геометрия: пока нет ни подтверждённой полной H1-пары, ни ранней линии по трём закрытым экстремумам."}
        {document.geometry_warmup_hours
          ? ` Предыстория для экстремумов: ${document.geometry_warmup_hours} ч.`
          : ""}
        {` Касаний 1–3: ${observedTouches.filter(item => item.kind === "MAIN_1H_TOUCH").length}; движений от линии: ${observedTouches.filter(item => item.kind === "MAIN_1H_REACTION").length}. Метки — наблюдения, не входы.`}
      </p>}
      {latestPriorBreak && <p className="replay-geometry-note"
        role="status" aria-label="Подтверждение слома приора H1">
        Слом приора H1: последняя часовая свеча закрылась за фиолетовым уровнем
        {" "}{latestPriorBreak.prior_price}, следующая открылась за ним.
        {" "}Новое направление: {latestPriorBreak.new_side === "BULL" ? "восходящее" : "нисходящее"}.
        {" "}{oppositeMainConfirmed
          ? "Противоположная жёлтая H1-линия подтверждена и отображается."
          : earlyMain?.side === latestPriorBreak.new_side
            ? "Предварительная противоположная жёлтая H1-линия показана по трём подтверждённым экстремумам; полной пары ещё нет."
            : "Противоположная жёлтая H1-линия ещё не подтверждена: ожидаются геометрические якоря."}
      </p>}
      {latestPrior && <p className="replay-geometry-note"
        role="status" aria-label="Приор H1">
        {priorAlreadyBroken ? "Исторический (сломанный) фиолетовый приор H1: " : "Фиолетовый приор H1: "}
        {latestPrior.price}
        {" · "}{latestPrior.side === "BULL" ? "LOW" : "HIGH"}
        {" · "}{priorAlreadyBroken
          ? "уровень уже сломан, остаётся только в истории."
          : "уровень второго подтверждённого касания трендовой."}{" "}Не торговый сигнал.
      </p>}
      {document.mode === "MARKET_ONLY" && document.h017_blue_risk_previews && cursor > 0 &&
        <p className="replay-geometry-note" role="status" aria-label="H-017 риск синей M5">
          Синяя M5: открытий за линией {blueRiskPreviews.length}, из них риск ≥1:1 — {blueRiskPreviews.filter(x => x.risk_status === "RISK_PASS").length}. Квадраты — исследовательские оценки по депозиту 200 USDT, не сделки.
        </p>}
      {document.mode === "MARKET_ONLY" && document.h017_blue_risk_previews && cursor > 0 &&
        <p className="replay-geometry-note" role="status" aria-label="H-017 сравнение DMI и исходов">
          H-017 · независимые сценарии касания фиксированных уровней для {visibleStudy.length} кандидатов ≥1R:
          {" "}цель раньше стопа {countTouch(visibleStudy, "TARGET_FIRST")},
          {" "}стоп раньше цели {countTouch(visibleStudy, "STOP_FIRST")},
          {" "}оба в одной M5 {countTouch(visibleStudy, "BOTH_SAME_M5")},
          {" "}ещё не определено {countTouch(visibleStudy, "UNRESOLVED")}.
          {" "}Пересечения DMI на последней ЗАКРЫТОЙ M5 до открытия:
          {" "}≥1 ({cohorts(true).length}): цель {countTouch(cohorts(true), "TARGET_FIRST")}, стоп {countTouch(cohorts(true), "STOP_FIRST")};
          {" "}0 ({cohorts(false).length}): цель {countTouch(cohorts(false), "TARGET_FIRST")}, стоп {countTouch(cohorts(false), "STOP_FIRST")};
          {" "}нет полного ADX/данных {visibleStudy.filter(row => row.crossings_at_open === null).length}.
          {" "}Без исполнения, без PnL; совпадение цели и стопа в одной свече не разрешается догадкой.
        </p>}
      {document.mode === "MARKET_ONLY" &&
        document.dmi_5m?.points.some(point => point.crossings !== undefined) && cursor > 0 &&
        <p className="replay-geometry-note" role="status" aria-label="Пересечения ADX/DMI">
          ADX/DMI · пересечений на закрытых M5: {dmiCrossings.length}.
          {dmiCrossings.length > 0 && ` Последнее: ${dmiCrossings.slice(-1)[0].side === "PLUS" ? "+DI" : "−DI"} ${dmiCrossings.slice(-1)[0].direction === "UP" ? "↑" : "↓"} ${dmiCrossings.slice(-1)[0].comparator === "OPPOSITE_DI" ? "противоположная DI" : dmiCrossings.slice(-1)[0].comparator === "ADX" ? "ADX" : "уровень 20"}.`}
          {" "}Пересечения — дополнительные аргументы, не входы и не обязательный фильтр.
        </p>}
      </details>
      {document.demo && <p className="replay-note">
        ДЕМО: синтетические свечи и условные события, не реальные сигналы стратегии и не результат Bybit.
      </p>}
      <div className="replay-grid">
        <section className="replay-chart-panel">
          <div className="replay-timeframe-switch" role="group" aria-label="Таймфрейм графика">
            <button type="button" aria-pressed={timeframe === "5m"}
              onClick={() => setTimeframe("5m")}>M5</button>
            <button type="button" aria-pressed={timeframe === "1h"}
              onClick={() => setTimeframe("1h")}>H1</button>
            <div className="replay-playback-controls" role="group" aria-label="Управление воспроизведением">
        <button type="button" onClick={() => { if (cursor === total) setCursor(0); setPlaying((s) => !s); }}>
          {playing ? "Пауза" : "▶ Пуск"}
        </button>
        <button type="button" onClick={() => {
          setPlaying(false);
          setCursor((current) => {
            const events = document.events;
            // Rewind one complete candle step, not just one trade/event row.
            const closed = events.slice(0, current).filter(event => event.kind === "CANDLE_CLOSED");
            if (closed.length <= 1) return 0;
            const previousClose = closed[closed.length - 2].time_ms;
            let next = 0;
            while (next < events.length && events[next].time_ms <= previousClose) next++;
            return next;
          });
        }} disabled={shown.candles.length === 0}>◀ Шаг назад</button>
        <button type="button" onClick={() => {
          setPlaying(false);
          setCursor((current) => {
            const events = document.events;
            const nextClose = events.findIndex((event, index) => index >= current && event.kind === "CANDLE_CLOSED");
            if (nextClose < 0) return total;
            const closeTime = events[nextClose].time_ms;
            let next = nextClose + 1;
            // All same-time trade actions belong to this candle step.
            while (next < total && events[next].time_ms === closeTime) next++;
            return next;
          });
        }} disabled={cursor >= total}>Шаг вперёд ▶</button>
        <button type="button" onClick={() => { setPlaying(false); setCursor(0); }}>В начало</button>
        <label className="replay-rate">Скорость {rate} событий/с
          <input type="range" min="1" max="60" value={rate} onChange={(e) => setRate(Number(e.target.value))} />
        </label>
            </div>
          </div>
          <div className="replay-drawing-tools" role="group" aria-label="Инструменты рисования">
            {REPLAY_DRAWING_TOOLS.map(({ tool, label }) => (
              <button type="button" key={tool} title={label} aria-label={label}
                aria-pressed={drawingTool === tool}
                onClick={() => { setDrawingTool(tool); setSelectedDrawing(null); }}>
                <ReplayToolIcon tool={tool} />
              </button>
            ))}
            <button type="button" disabled={!selectedDrawing}
              onClick={() => {
                setDrawings(current => current.filter(d => d.id !== selectedDrawing));
                setSelectedDrawing(null);
              }} title="Удалить выбранное" aria-label="Удалить выбранное"><ReplayToolIcon tool="delete" /></button>
            <span className="replay-drawing-count" aria-live="polite">Ручных линий: {drawings.length}</span>
          </div>
          <ReplayChart document={document} cursor={cursor} showDebug={showDebug} timeframe={timeframe}
            drawings={drawings} selectedId={selectedDrawing} drawingTool={drawingTool}
            onDrawingsChange={setDrawings} onSelectDrawing={setSelectedDrawing}
            onDrawingGesture={() => setPlaying(false)} />
        </section>
        <aside className="replay-events" aria-label="Журнал событий">
          <h2>События</h2>
          {lastTimeline.length === 0 && <p>Нажмите «Пуск» или «Шаг».</p>}
          {lastTimeline.map((item) => (
            <div className="replay-event" key={item.key}>
              <time>{new Date(item.time_ms).toLocaleTimeString("ru-RU", { timeZone: "UTC" })} UTC</time>
              {item.kind === "REPLAY" ? <>
                <strong>{label(item.event)}</strong>
                {item.event.price !== undefined && <span>{item.event.price}</span>}
                {item.event.trade_id && <small>{item.event.trade_id}</small>}
              </> : <>
                <strong>Слом приора H1 · {item.breakEvent.new_side === "BULL" ? "восходящий" : "нисходящий"} тренд</strong>
                <span>{item.breakEvent.prior_price}</span>
              </>}
            </div>
          ))}
        </aside>
      </div>
      <footer className="replay-footer">
        {cursor} из {total} событий. Вход на следующем открытии не раскрывает будущую свечу.
        Только публичные GET-запросы к истории Bybit; без приватных API, торговли и записи в PAPER.
      </footer>
    </main>
  );
}
