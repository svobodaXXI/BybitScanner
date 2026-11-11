import {
  CandlestickSeries, ColorType, CrosshairMode, LineSeries, LineStyle, createChart,
  type IChartApi, type ISeriesApi, type Logical, type UTCTimestamp,
} from "lightweight-charts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  completeHourlyCandles, nextClosedCandleCursor, parseReplayDocument, syntheticReplay, simulationActionJournal, visibleReplay, visibleGeometry, visibleGeometryHistory, visibleEarlyGeometry, earlyGeometryTimeline, visibleEarlyGeometryTimeline, visiblePriorLevels, visiblePriorBreaks, visibleDmi, visibleObservations,
  visibleH017BlueRiskPreviews, studyH017BlueCandidates, visibleH017CandidateStudy,
  type ReplayDocument, type ReplayEvent,
} from "./replayModel";
import { visibleExecutionMarkers, TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR } from "./executionMarkers";
import {
  matchPaperFactsToMarket, parsePaperEpisodeFacts, revealedPaperMarkers,
  type PaperEpisodeFacts, type PaperOverlay,
} from "./paperEpisodeFacts";
import { rayEndPoint } from "../chart/drawingGeometry";
import { DrawingOverlay } from "../chart/DrawingOverlay";
import type { DrawingObject, DrawingTool } from "../chart/drawingModel";
import { chartLogicalAtTime, drawingLogicalToTime, timeAtChartLogical, timeToDrawingLogical } from "./replayDrawingCoordinates";
import { RunSetupPanel } from "./RunSetupPanel";
import { validateInclusiveWindow, makeWedgeRunRequest, formatRunCoordinates, onlyWedges, type RunSelection } from "./runSetup";
type WedgeRunRequest = ReturnType<typeof makeWedgeRunRequest>;
import "./replay.css";

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
const REPLAY_TOOL_PATHS: Record<DrawingTool | "delete" | "undo", string> = {
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
  undo: "M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-2",
};
function ReplayToolIcon({ tool }: { tool: DrawingTool | "delete" | "undo" }) {
  return <svg className="replay-tool-icon" viewBox="0 0 24 24"
    data-tool-icon={tool} aria-hidden="true" focusable="false">
    <path d={REPLAY_TOOL_PATHS[tool]} />
  </svg>;
}
const PLAYER_PATHS = {
  play: "M7 4L20 12L7 20Z",
  pause: "M6 4h4v16H6zM14 4h4v16h-4z",
  backward: "M12 5L4 12L12 19ZM21 5L13 12L21 19Z",
  forward: "M3 5L11 12L3 19ZM12 5L20 12L12 19Z",
  beginning: "M4 4v16M20 5L11 12L20 19ZM11 5L2 12L11 19Z",
} as const;
function PlayerIcon({ name }: { name: keyof typeof PLAYER_PATHS }) {
  return <svg className="replay-player-icon" viewBox="0 0 24 24"
    data-player-icon={name} aria-hidden="true" focusable="false">
    <path d={PLAYER_PATHS[name]} />
  </svg>;
}
function ReplayChart({ document, cursor, paperOverlay, paperFacts, showTrendGeometry, showDebug, timeframe, drawings, selectedId,
  drawingTool, onDrawingsChange, onSelectDrawing, onDrawingGesture }: {
  document: ReplayDocument; cursor: number; paperOverlay: PaperOverlay;
  paperFacts: PaperEpisodeFacts | null; showTrendGeometry: boolean; showDebug: boolean; timeframe: "5m" | "1h";
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
  // Build a frozen visual-only record once per archive. Each already
  // revealed provisional line persists as drawn; rewinding masks its future.
  const earlyTimeline = useMemo(() => earlyGeometryTimeline(document), [document]);
  const earlyGeometry = useMemo(
    () => visibleEarlyGeometryTimeline(earlyTimeline, shown.lastTimeMs),
    [earlyTimeline, shown.lastTimeMs],
  );
  const observedDmi = useMemo(() => visibleDmi(document, shown.candles.length), [document, shown.candles.length]);
  // Only the final 5m DMI reading of each completed H1 is plotted on the H1 axis.
  const indicatorSamples = timeframe === "1h"
    ? displayCandles.map(hour => {
      const index = shown.candles.findIndex(bar => bar.end_ms === hour.end_ms);
      return index >= 0 ? observedDmi[index] : undefined;
    })
    : observedDmi;
  const observedTouches = useMemo(() =>
    showTrendGeometry ? visibleObservations(document, shown.lastTimeMs) : [],
    [document, shown.lastTimeMs, showTrendGeometry]);
  const blueRiskPreviews = useMemo(
    () => showTrendGeometry ? visibleH017BlueRiskPreviews(document, shown.lastTimeMs) : [],
    [document, shown.lastTimeMs, showTrendGeometry],
  );
  const priorBreaks = useMemo(
    () => showTrendGeometry ? visiblePriorBreaks(document, shown.lastTimeMs) : [],
    [document, shown.lastTimeMs, showTrendGeometry],
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
      const knownLines = showTrendGeometry ? visibleGeometry(document, shown.lastTimeMs) : [];
      const historicalLines = showTrendGeometry ? visibleGeometryHistory(document, shown.lastTimeMs) : [];
      // Both published and provisional history are immutable visual records:
      // a replaced slope cannot erase, relocate or backdate its predecessor.
      // Avoid double-painting an early guide with identical confirmed anchors.
      const confirmedKeys = new Set(historicalLines.map(line =>
        [line.kind, line.side, line.from_ms, line.to_ms, line.from_price, line.to_price].join(":")));
      const drawableLines = [...historicalLines, ...(showTrendGeometry ? earlyGeometry : []).filter(line =>
        !confirmedKeys.has([line.kind, line.side, line.from_ms, line.to_ms, line.from_price, line.to_price].join(":")))];
      const knownPriors = showTrendGeometry ? visiblePriorLevels(document, shown.lastTimeMs) : [];
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
      // Source-original detector geometry is read-only archive evidence and
      // DISTINCT from the dynamically computed yellow H1 / blue M5 lines.
      // The exact anchors are never refitted to candles; no pre-signal leak.
      const original = paperOverlay.status === "MATCHED" &&
        paperFacts?.setup_context?.status === "EXACT_D2_LINK" &&
        paperFacts.setup_context.geometry_status === "ORIGINAL_ARCHIVE_HASH_VERIFIED"
        ? paperFacts.setup_context.original_geometry : undefined;
      let paintedOriginal = 0;
      if (original && shown.lastTimeMs !== null && shown.lastTimeMs >= original.sent_at_ms
          && displayCandles.length >= 2) {
        const oldest = displayCandles[0].start_ms;
        const newest = displayCandles[displayCandles.length - 1].start_ms;
        for (const boundary of original.boundaries) {
          const first = boundary.anchors[0];
          const last = boundary.anchors[boundary.anchors.length - 1];
          const startAt = boundary.kind === "horizontal"
            ? oldest : Math.max(oldest, first.bar_open_time_ms);
          const endAt = boundary.kind === "segment"
            ? Math.min(newest, last.bar_open_time_ms) : newest;
          // Map only to actual already-revealed chart bars; original time
          // prices still come from the immutable anchor formula.
          const leftBar = displayCandles.find(bar => bar.start_ms >= startAt);
          const rightBar = displayCandles.slice().reverse().find(bar => bar.start_ms <= endAt);
          if (!leftBar || !rightBar || leftBar.start_ms >= rightBar.start_ms) continue;
          const priceAt = (at: number) => boundary.anchors.length === 1 ? first.price :
            first.price + (last.price - first.price) *
              (at - first.bar_open_time_ms) / (last.bar_open_time_ms - first.bar_open_time_ms);
          const x1 = api.timeScale().timeToCoordinate((leftBar.start_ms / 1000) as UTCTimestamp);
          const x2 = api.timeScale().timeToCoordinate((rightBar.start_ms / 1000) as UTCTimestamp);
          const y1 = candleSeries.priceToCoordinate(priceAt(leftBar.start_ms));
          const y2 = candleSeries.priceToCoordinate(priceAt(rightBar.start_ms));
          if (x1 === null || x2 === null || y1 === null || y2 === null ||
              !Number.isFinite(x1) || !Number.isFinite(x2) ||
              !Number.isFinite(y1) || !Number.isFinite(y2)) continue;
          const to = boundary.kind === "ray" || boundary.kind === "horizontal-ray"
            ? rayEndPoint({ x: x1, y: y1 }, { x: x2, y: y2 },
                { width: priceWidth, height: paneHeight })
            : { x: x2, y: y2 };
          context.beginPath();
          context.strokeStyle = "#d08cf0";
          context.lineWidth = 1.25;
          context.setLineDash([3, 4]);
          context.moveTo(x1, y1);
          context.lineTo(to.x, to.y);
          context.stroke();
          paintedOriginal++;
        }
        context.setLineDash([]);
      }
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
      for (const item of (showTrendGeometry && showDebug ? observedTouches : [])) {
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
      for (const item of (showTrendGeometry && showDebug ? blueRiskPreviews : [])) {
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
      // PAPER observations are a separate, hollow-ring overlay. These are
      // original owner-imported execution prices, NOT SIMULATION fill events.
      // Only plot a factual fill once its independently closed M5 is revealed.
      let paintedPaper = 0;
      for (const fill of revealedPaperMarkers(paperOverlay, shown.candles)) {
        const stamp = timeframe === "1h"
          ? Math.floor(fill.candle_start_ms / 3_600_000) * 3_600_000
          : fill.candle_start_ms;
        if (!displayCandles.some(bar => bar.start_ms === stamp)) continue;
        const x = api.timeScale().timeToCoordinate((stamp / 1000) as UTCTimestamp);
        const y = candleSeries.priceToCoordinate(fill.price);
        if (x === null || y === null || !Number.isFinite(x) || !Number.isFinite(y) ||
            x < 0 || x > priceWidth || y < 0 || y > paneHeight) continue;
        context.beginPath();
        context.arc(x, y, 5.5, 0, 2 * Math.PI);
        context.fillStyle = "#121923";
        context.fill();
        context.strokeStyle = fill.order_side === "Buy" ? TELEGRAM_BUY_COLOR : TELEGRAM_SELL_COLOR;
        context.lineWidth = 2;
        context.stroke();
        paintedPaper++;
      }
      context.restore();
      canvas.dataset.visibleFills = String(rendered);
      canvas.dataset.visiblePaperFills = String(paintedPaper);
      canvas.dataset.visibleOriginalGeometry = String(paintedOriginal);
      canvas.dataset.visibleGeometry = String(knownLines.length);
      canvas.dataset.visibleEarlyGeometry = String(showTrendGeometry ? earlyGeometry.length : 0);
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
  }, [shown, document, cursor, paperOverlay, paperFacts, observedDmi, observedTouches, blueRiskPreviews, priorBreaks, showTrendGeometry, showDebug, timeframe, displayCandles, earlyGeometry]);

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
          aria-hidden="true" data-visible-fills="0" data-visible-paper-fills="0" data-visible-original-geometry="0" data-visible-observations="0" data-visible-blue-risk="0" />
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

export function ReplayPage() {
  const [document, setDocument] = useState<ReplayDocument>(() => syntheticReplay());
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [selectedStrategies, setSelectedStrategies] = useState<RunSelection>(onlyWedges);
  const showTrendGeometry = selectedStrategies.selected.includes("H1_TREND");
  const showSelectedWedges = selectedStrategies.selected.includes("WEDGE_RISING") ||
    selectedStrategies.selected.includes("WEDGE_FALLING");
  const symbolEdited = useRef(false);
  const currentSymbol = useRef(symbol);
  currentSymbol.current = symbol;
  const onPasteSymbol = useCallback((nextSymbol: string) => {
    symbolEdited.current = true;
    setSymbol(nextSymbol);
  }, []);
  const acceptArchiveSymbol = useCallback((archiveSymbol: string): boolean => {
    if (symbolEdited.current) return currentSymbol.current === archiveSymbol;
    if (currentSymbol.current === "BTCUSDT") {
      setSymbol(archiveSymbol);
      return true;
    }
    return currentSymbol.current === archiveSymbol;
  }, []);
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
  const [fileLabel, setFileLabel] = useState("Тикер и период не выбраны");
  // PAPER evidence is never inserted into document.events or VirtualAccount.
  const [paperFacts, setPaperFacts] = useState<PaperEpisodeFacts | null>(null);
  const paperOverlay = useMemo(
    () => matchPaperFactsToMarket(paperFacts, document), [paperFacts, document],
  );
  // The synthetic fixture is available only via the explicit Example button.
  const [simulationGraphPending, setSimulationGraphPending] = useState(true);
  const [preparedRun, setPreparedRun] = useState(false);
  const [runLoading, setRunLoading] = useState(false);
  const [runWaitingSeconds, setRunWaitingSeconds] = useState(0);
  const [playRequestId, setPlayRequestId] = useState(0);

  useEffect(() => {
    if (!runLoading) { setRunWaitingSeconds(0); return; }
    const since = Date.now();
    const ticker = window.setInterval(
      () => setRunWaitingSeconds(Math.floor((Date.now() - since) / 1000)), 1000,
    );
    return () => window.clearInterval(ticker);
  }, [runLoading]);
  const shown = useMemo(() => visibleReplay(document.events, cursor), [document, cursor]);
  const journal = useMemo(() => (document.demo ? [] : document.events.slice(0, cursor))
    .filter(event => event.kind !== "CANDLE_CLOSED").map(event => {
      const fmt = (value: string) => {
        const number = Number(value);
        return number > 0 ? "+" + number.toFixed(4) : number.toFixed(4);
      };
      let message: string;
      switch (event.kind) {
        case "WEDGE_ACCEPTED":
          message = "Обнаружен паттерн: " + (event.pattern === "Rising Wedge"
            ? "восходящий клин" : "нисходящий клин") +
            ". Кандидат принят. Ожидается пробой"; break;
        case "WEDGE_BREAKOUT": message = "Пробой подтверждён. Ожидается ретест"; break;
        case "WEDGE_RETEST": message = "Ретест подтверждён"; break;
        case "ENTRY_SIGNAL": message = "Выставлен LIMIT после ретеста"; break;
        case "ENTRY_FILLED": message = "Позиция открыта, вход по ретесту"; break;
        case "EXIT_FILLED":
          message = "Позиция закрыта (" +
            (event.reason === "STOP" ? "STOP" : event.reason === "TAKE" ? "TAKE" : "выход") +
            ")" + (event.net_usdt !== undefined && event.pnl_percent !== undefined
              ? ": " + fmt(event.net_usdt) + " USDT · " + fmt(event.pnl_percent) + "%"
              : " · результат недоступен"); break;
        default: message = "Событие";
      }
      return { sequence: event.sequence, time: event.time_ms, message };
    }), [document.events, cursor]);
  const paperSetupContext = paperFacts?.setup_context;
  const paperSetupVisible = paperSetupContext?.status === "EXACT_D2_LINK" &&
    paperOverlay.status === "MATCHED" && shown.lastTimeMs !== null &&
    shown.lastTimeMs >= paperSetupContext.setup.created_at_ms;
  // D2 observations remain outside SIMULATION events/journal/PnL. Like
  // candles, a D2 decision cannot be seen until its timestamp is reached.
  const paperDecisionObservations = useMemo(() =>
    paperFacts?.setup_context?.status === "EXACT_D2_LINK" &&
    paperOverlay.status === "MATCHED" && shown.lastTimeMs !== null
      ? paperFacts.setup_context.decisions.filter(e => e.occurred_at_ms <= shown.lastTimeMs!)
      : [], [paperFacts, paperOverlay, shown.lastTimeMs]);

  const total = document.events.length;
  const progress = Math.round(100 * cursor / total);
  const seekPoints = useMemo(() => {
    const result = [0];
    for (let i = 0; i < document.events.length; i++) {
      const closed = document.events[i];
      if (closed.kind !== "CANDLE_CLOSED") continue;
      let next = i + 1;
      while (next < document.events.length &&
             document.events[next].time_ms === closed.time_ms) next++;
      if (next > result[result.length - 1]) result.push(next);
      i = next - 1;
    }
    return result;
  }, [document.events]);
  const seekIndex = Math.max(0, seekPoints.indexOf(cursor));
  const priorBreaks = useMemo(
    () => showTrendGeometry ? visiblePriorBreaks(document, shown.lastTimeMs) : [],
    [document, shown.lastTimeMs, showTrendGeometry],
  );
  const latestPriorBreak = priorBreaks.at(-1);
  const publishedGeometry = useMemo(
    () => showTrendGeometry ? visibleGeometry(document, shown.lastTimeMs) : [],
    [document, shown.lastTimeMs, showTrendGeometry],
  );
  const earlyGeometry = useMemo(
    () => showTrendGeometry ? visibleEarlyGeometry(document, shown.lastTimeMs) : [],
    [document, shown.lastTimeMs, showTrendGeometry],
  );
  const earlyMain = earlyGeometry.find(line => line.kind === "MAIN_1H");
  const earlyBlueCount = earlyGeometry.filter(line => line.kind === "REFERENCE_5M").length;
  const activeMain = publishedGeometry.find(line => line.kind === "MAIN_1H");
  const latestPrior = useMemo(
    () => showTrendGeometry ? visiblePriorLevels(document, shown.lastTimeMs).at(-1) : undefined,
    [document, shown.lastTimeMs, showTrendGeometry],
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
  const observedTouches = useMemo(() =>
    showTrendGeometry ? visibleObservations(document, shown.lastTimeMs) : [],
    [document, shown.lastTimeMs, showTrendGeometry]);
  const blueRiskPreviews = useMemo(
    () => showTrendGeometry ? visibleH017BlueRiskPreviews(document, shown.lastTimeMs) : [],
    [document, shown.lastTimeMs, showTrendGeometry],
  );
  const dmiCrossings = useMemo(
    () => visibleDmi(document, shown.candles.length).flatMap(point => point.crossings ?? []),
    [document, shown.candles.length],
  );
  const retrospectiveStudy = useMemo(
    () => showTrendGeometry ? studyH017BlueCandidates(document) : [],
    [document, showTrendGeometry]);
  const visibleStudy = useMemo(
    () => visibleH017CandidateStudy(retrospectiveStudy, shown.lastTimeMs),
    [retrospectiveStudy, shown.lastTimeMs],
  );
  const cohorts = (withCross: boolean) => visibleStudy.filter(row =>
    row.crossings_at_open !== null && (row.crossings_at_open.length > 0) === withCross);
  const countTouch = (rows: typeof visibleStudy, kind: typeof visibleStudy[number]["first_touch"]) =>
    rows.filter(row => row.first_touch === kind).length;
  const fileInput = useRef<HTMLInputElement>(null);
  const paperFileInput = useRef<HTMLInputElement>(null);

  const onSimulationStart = useCallback((request: WedgeRunRequest) => {
    // A new ticker/date must never inherit old candles or demonstration fills.
    bundledRequest.current?.abort(); bundledRequest.current = null;
    historyRequest.current?.abort(); historyRequest.current = null;
    setHistoryLoading(false);
    setPlaying(false); setCursor(0);
    setError(null);
    setDrawings([]); setSelectedDrawing(null); setDrawingTool("crosshair");
    setFileLabel(formatRunCoordinates(request.symbol, request.start_utc, request.end_utc_inclusive));
    setSimulationGraphPending(true);
    setPreparedRun(true);
    setRunLoading(false);
  }, []);

  const onSimulationAppend = useCallback((runId: string, events: ReplayEvent[]) => {
    setDocument(previous => previous.simulation_run_id === runId
      ? { ...previous, events: [...previous.events, ...events] }
      : previous);
  }, []);
  const onSimulationFailed = useCallback(() => {
    setPlaying(false);
    setSimulationGraphPending(true);
    setPreparedRun(true);
    setCursor(0);
  }, []);
  const onSimulationReady = useCallback((replay: ReplayDocument) => {
    if (replay.mode !== "STRATEGY" || replay.demo || !replay.symbol) {
      throw new Error("Новый прогон не содержит проверенной истории");
    }
    symbolEdited.current = true;
    setSymbol(replay.symbol);
    setDocument(replay);
    setCursor(0); setTimeframe("5m");
    // The owner-selected ticker and date range stay visible in Source.
    setSimulationGraphPending(false);
    setPreparedRun(false);
    setPlaying(true);
  }, []);

  function syncImportedMarketSelection(parsed: ReplayDocument) {
    if (parsed.symbol) {
      symbolEdited.current = true;
      setSymbol(parsed.symbol);
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
        setSimulationGraphPending(false);
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

  // Keep the requested candle cadence independent of network packet arrivals.
  // A batch may contain many verified bars, but each timer tick reveals ONE M5.
  // A stalled Scanner frontier costs no playback time: never catch up in a burst.
  const availableEvents = useRef(document.events);
  availableEvents.current = document.events;
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setCursor(current => nextClosedCandleCursor(availableEvents.current, current));
    }, Math.max(16, 1000 / rate));
    return () => window.clearInterval(timer);
  }, [playing, rate]);

  useEffect(() => {
    // Do not stop when playback reaches the still-growing verified frontier.
    if (cursor >= total && !runLoading) setPlaying(false);
  }, [cursor, total, runLoading]);

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
      setSimulationGraphPending(false);
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

  async function loadPaperFacts(file?: File) {
    if (!file) return;
    setPlaying(false);
    setPaperFacts(null); // Invalid replacement must not leave previous PAPER marks displayed.
    try {
      if (file.size > 4 * 1024 * 1024)
        throw new Error("JSON PAPER больше 4 МБ");
      const imported = parsePaperEpisodeFacts(JSON.parse(await file.text() as string) as unknown);
      setPaperFacts(imported);
      setError(null);
      // Instant inspection only when the selected, independently verified
      // public M5 archive already covers every fact. Otherwise do not
      // substitute a candle, download private history or invent a chart.
      if (matchPaperFactsToMarket(imported, document).status === "MATCHED") {
        setCursor(document.events.length);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось прочитать факты PAPER");
    } finally {
      if (paperFileInput.current) paperFileInput.current.value = "";
    }
  }

  async function loadLocalHistory(selectedSymbol: string, selectedStart: string, selectedEnd: string) {
    bundledRequest.current?.abort(); bundledRequest.current = null;
    historyRequest.current?.abort();
    const controller = new AbortController();
    historyRequest.current = controller;
    setHistoryLoading(true);
    setPlaying(false);
    setError(null);
    try {
      const window = validateInclusiveWindow(selectedStart, selectedEnd);
      // The legacy read-only public market loader accepts full UTC days,
      // maximum 7; it cannot silently turn a minute interval into whole days.
      if (window.startMs % 86_400_000 || window.endExclusiveMs % 86_400_000 ||
          window.minutes > 7 * 1440) {
        throw new Error("Публичный Bybit M5: выберите полные UTC-дни, не более 7. Для точных минут используйте SIMULATION.");
      }
      const query = new URLSearchParams({
        symbol: selectedSymbol.trim().toUpperCase(),
        start: new Date(window.startMs).toISOString().slice(0, 10),
        end: new Date(window.endExclusiveMs).toISOString().slice(0, 10),
      });
      // Only the loopback Python viewer implements this research-only GET.
      // Never call /api: Vite's /api proxy belongs to the main PAPER backend.
      const response = await fetch("/local-replay/history?" + query.toString(), {
        method: "GET", cache: "no-store", signal: controller.signal,
      });
      // Loopback returns plain-text errors (not JSON) for 400/502.
      // A JSON.parse exception here previously concealed the actual failure.
      // Public M5 never creates the local verified M1 + risk prerequisites
      // for a SIMULATION strategy run.
      if (!response.ok) {
        if (response.status === 502) {
          throw new Error("Публичный Bybit M5 недоступен (HTTP 502): запрос к рыночному API не завершился. График не загружен. Локальный торговый прогон отдельно требует архив M1 и профиль риска.");
        }
        const reason = (await response.text()).slice(0, 260).trim();
        throw new Error(`Ошибка публичной истории HTTP ${response.status}: ${reason || "нет данных"}`);
      }
      const raw: unknown = await response.json();
      const imported = parseReplayDocument(raw);
      if (imported.mode !== "MARKET_ONLY") throw new Error("История не соответствует режиму MARKET_ONLY");
      if (historyRequest.current !== controller) return;
      setDocument(imported);
      setSimulationGraphPending(false);
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

      <RunSetupPanel symbol={symbol} onArchiveSymbol={acceptArchiveSymbol}
        onPasteSymbol={onPasteSymbol} onSimulationStart={onSimulationStart}
        onSimulationReady={onSimulationReady} onSimulationAppend={onSimulationAppend}
        onSimulationFailed={onSimulationFailed} onSimulationBusy={setRunLoading}
        playRequestId={playRequestId} showReport={!simulationGraphPending && !runLoading && cursor >= total}
        onPublicHistoryRequest={(ticker, from, to) => void loadLocalHistory(ticker, from, to)}
        publicHistoryLoading={historyLoading}
        onStrategySelectionChange={setSelectedStrategies} />
      <section className="replay-controls" aria-label="Управление воспроизведением">
        <label className="replay-file">
          Загрузить JSON прогона
          <input ref={fileInput} type="file" accept=".json,application/json" disabled={runLoading}
            onChange={(e) => void loadFile(e.target.files?.[0])} />
        </label>
        <label className="replay-file">
          Импорт JSON сделки PAPER
          <input ref={paperFileInput} aria-label="Импорт JSON сделки PAPER"
            type="file" accept=".json,application/json" disabled={runLoading}
            onChange={(e) => void loadPaperFacts(e.target.files?.[0])} />
        </label>
        {paperFacts && <button type="button" onClick={() => setPaperFacts(null)}>
          Убрать факты PAPER
        </button>}
        <button type="button" onClick={() => {
          bundledRequest.current?.abort(); bundledRequest.current = null;
          historyRequest.current?.abort(); historyRequest.current = null;
          setHistoryLoading(false); setPlaying(false); setCursor(0); setError(null);
          setDocument(syntheticReplay()); setSimulationGraphPending(false);
          setPreparedRun(false);
          setFileLabel("Синтетический пример");
          setDrawings([]); setSelectedDrawing(null); setDrawingTool("crosshair");
        }}>Пример</button>
        <button type="button" aria-label="Скачать журнал SIMULATION JSON"
          disabled={simulationGraphPending} onClick={() => {
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
        }}>Журнал JSON ({simulationGraphPending ? 0 : simulationActionJournal(document).actions.length})</button>

      </section>

      {error && <p role="alert" className="replay-error">{error}</p>}
      {paperFacts && <p className="replay-note" role="status" aria-label="PAPER факты сделки">
        PAPER · {paperFacts.symbol} · {paperFacts.trade_episode_id}
        {" · "}{paperFacts.execution_allocations.length} фактических исполнений
        {" · "}{paperOverlay.status === "MATCHED"
          ? "Кружки на закрытых свечах · цена оригинального исполнения"
          : paperOverlay.reason}
        {" · "}PnL по цене и известным комиссиям: {paperFacts.pnl_usdt} USDT
        {" · "}JSON без криптографической подписи; не виртуальные сделки и не решения Robot.
        {paperSetupContext && (
          paperSetupContext.status !== "EXACT_D2_LINK"
            ? " · D2: нет подтверждённой связи с исходным setup"
            : paperSetupVisible
              ? ` · D2: ${paperSetupContext.setup.pattern} · ${paperSetupContext.setup.timeframe} · версия ${paperSetupContext.setup.strategy_version}` +
                (paperSetupContext.geometry_status !== "ORIGINAL_ARCHIVE_HASH_VERIFIED"
                  ? " · исходная геометрия не экспортирована"
                  : shown.lastTimeMs !== null &&
                    shown.lastTimeMs >= paperSetupContext.original_geometry!.sent_at_ms
                    ? " · лиловая пунктирная: архивная исходная геометрия (только наблюдение, неподписанный JSON)"
                    : " · архивная геометрия появится после времени исходного сигнала")
              : " · D2: исходный setup появится после его подтверждённого времени на графике"
        )}
      </p>}
      {simulationGraphPending && <p className="replay-note" role="status"
        aria-label="Ожидание нового графика">
        {runLoading ? "Проверяю архив и рассчитываю виртуальный прогон…" :
          preparedRun ? "Тикер и период применены. Нажмите ▶ Пуск." :
            "Вставьте тикер и период, нажмите «Применить», затем ▶ Пуск."}
        {" "}Старые и демонстрационные свечи не показываются.
      </p>}
      <section className="replay-meta" aria-label="Состояние симулятора">
        <div><span>Источник</span><strong>{fileLabel}</strong></div>
        <div><span>Время рынка</span><strong>{simulationGraphPending ? "До начала прогона" :
          shown.lastTimeMs === null ? "До первого события" :
          new Date(shown.lastTimeMs).toLocaleString("ru-RU", { timeZone: "UTC" }) + " UTC"}</strong></div>
        <div><span>Свечи / входы / выходы</span>
          <strong>{simulationGraphPending ? "0 / 0 / 0" :
            `${shown.candles.length} / ${shown.fills.length} / ${shown.exits.length}`}</strong></div>
      </section>
      {!simulationGraphPending && <>
      <div className="replay-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={progress} aria-label="Прогресс воспроизведения">
        <div style={{ width: progress + "%" }} />
      </div>
      {document.mode === "MARKET_ONLY" && <p className="replay-note">
        РЕАЛЬНЫЕ СВЕЧИ BYBIT · БЕЗ СДЕЛОК:
        {" "}{document.market_data_source === "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M"
          ? "исторические сделки из официального публичного архива, агрегированные в закрытые 5m OHLCV"
          : "публичные свечи API Bybit"}
        {" "}{showTrendGeometry
          ? "Трендовые H1/M5 выбраны: жёлтые H1 и синие M5 — исследовательская геометрия, не торговые сигналы."
          : "Трендовые H1/M5 выключены: их линии и приор скрыты."}
        {" "}{showSelectedWedges
          ? "Клинья выбраны, но публичный M5-просмотр не запускает Scanner: клинья здесь не искались. Для торгового прогона нужны проверенные M1 и профиль риска."
          : "Клинья не выбраны и в публичном M5-просмотре не искались."}
      </p>}
      <details className="replay-diagnostics">
        <summary>Диагностика</summary>
        <label><input type="checkbox" checked={showDebug} onChange={(e) => setShowDebug(e.target.checked)} /> Показать опорные маркеры</label>
      {document.mode === "MARKET_ONLY" && showTrendGeometry && cursor > 0 && <p className="replay-geometry-note"
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
      {document.mode === "MARKET_ONLY" && showTrendGeometry && document.h017_blue_risk_previews && cursor > 0 &&
        <p className="replay-geometry-note" role="status" aria-label="H-017 риск синей M5">
          Синяя M5: открытий за линией {blueRiskPreviews.length}, из них риск ≥1:1 — {blueRiskPreviews.filter(x => x.risk_status === "RISK_PASS").length}. Квадраты — исследовательские оценки по депозиту 200 USDT, не сделки.
        </p>}
      {document.mode === "MARKET_ONLY" && showTrendGeometry && document.h017_blue_risk_previews && cursor > 0 &&
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
      </>}
      <div className="replay-grid">
        <section className="replay-chart-panel">
          <div className="replay-timeframe-switch" role="group" aria-label="Таймфрейм графика">
            <strong className="replay-chart-symbol" aria-label="Тикер графика">
              {document.symbol?.replace(/USDT$/, "") || "—"}
            </strong>
            <button type="button" disabled title="Нет проверенной минутной истории в потоке графика">M1</button>
            <button type="button" disabled title="Нет исходной ленты сделок для 15-секундного графика">15с</button>
            <button type="button" aria-pressed={timeframe === "5m"}
              onClick={() => setTimeframe("5m")}>M5</button>
            <button type="button" aria-pressed={timeframe === "1h"}
              onClick={() => setTimeframe("1h")}>H1</button>
            <div className="replay-playback-controls" role="group" aria-label="Управление воспроизведением">
        <button type="button" className="replay-player-button"
          title={playing ? "Пауза" : "Пуск"} aria-label={playing ? "Пауза" : "Пуск"}
          disabled={simulationGraphPending && (runLoading || !preparedRun)}
          onClick={() => {
            if (simulationGraphPending) { setPlayRequestId(id => id + 1); return; }
            if (cursor === total) setCursor(0);
            setPlaying(s => !s);
          }}>
          <PlayerIcon name={playing ? "pause" : "play"} />
        </button>
        <button type="button" className="replay-player-button" title="Шаг назад"
          aria-label="Шаг назад" onClick={() => {
            setPlaying(false);
            setCursor(seekPoints[Math.max(0, seekIndex - 1)]);
          }} disabled={simulationGraphPending || shown.candles.length === 0}><PlayerIcon name="backward" /></button>
        <button type="button" className="replay-player-button" title="Шаг вперёд"
          aria-label="Шаг вперёд" onClick={() => {
            setPlaying(false);
            setCursor((current) => nextClosedCandleCursor(document.events, current));
          }} disabled={simulationGraphPending || cursor >= total}><PlayerIcon name="forward" /></button>
        <button type="button" className="replay-player-button" title="В начало"
          aria-label="В начало" disabled={simulationGraphPending}
          onClick={() => { setPlaying(false); setCursor(0); }}>
          <PlayerIcon name="beginning" />
        </button>
        <input className="replay-seek" type="range" min={0} max={seekPoints.length - 1}
                step={1} value={simulationGraphPending ? 0 : seekIndex}
                disabled={simulationGraphPending} aria-label="Перемотка воспроизведения"
                onChange={e => {
                  setPlaying(false);
                  setCursor(seekPoints[Number(e.target.value)]);
                }} />
        <label className="replay-rate">Скорость {rate} свечей/с
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
            <button type="button" disabled={drawings.length === 0}
              onClick={() => {
                setPlaying(false);
                setDrawings(current => current.slice(0, -1));
                setSelectedDrawing(null);
              }} title="Отменить последнюю фигуру" aria-label="Отменить последнюю фигуру">
              <ReplayToolIcon tool="undo" />
            </button>
            <button type="button" disabled={!selectedDrawing}
              onClick={() => {
                setDrawings(current => current.filter(d => d.id !== selectedDrawing));
                setSelectedDrawing(null);
              }} title="Удалить выбранное" aria-label="Удалить выбранное"><ReplayToolIcon tool="delete" /></button>
            <span className="replay-drawing-count" aria-live="polite">Ручных линий: {drawings.length}</span>
          </div>
          {simulationGraphPending
            ? <div className="replay-chart-pending" aria-label="Пустой график до запуска">
                {runLoading ? `Проверяю первые M1: ${runWaitingSeconds} с. Затем свечи появятся постепенно.` :
                  "График нового прогона появится после нажатия ▶"}
              </div>
            : <ReplayChart document={document} cursor={cursor} paperOverlay={paperOverlay}
                paperFacts={paperFacts} showTrendGeometry={showTrendGeometry}
                showDebug={showDebug} timeframe={timeframe}
                drawings={drawings} selectedId={selectedDrawing} drawingTool={drawingTool}
                onDrawingsChange={setDrawings} onSelectDrawing={setSelectedDrawing}
                onDrawingGesture={() => setPlaying(false)} />}
        </section>
        <aside className="replay-events" aria-label="Журнал событий">
          <h2>Журнал событий</h2>
          <div className="replay-events-list" aria-live="off">
            {journal.length === 0 && <p>Ожидаю события Scanner и Robot</p>}
            {paperDecisionObservations.length > 0 && (
              <section aria-label="Наблюдения PAPER D2" className="replay-d2-observations">
                <strong>Подтверждённые наблюдения D2 · не полный журнал Robot</strong>
                {paperDecisionObservations.map(event => (
                  <div className="replay-events-item" key={event.decision_event_id}>
                    <time>{new Date(event.occurred_at_ms).toLocaleString("ru-RU", {
                      timeZone: "UTC", day: "2-digit", month: "2-digit",
                      hour: "2-digit", minute: "2-digit",
                    })} UTC</time>
                    <span>{event.kind}: {event.previous_state ?? "—"} → {event.next_state} · {event.reason_code}</span>
                    <span>Источник: {event.controller}</span>
                  </div>
                ))}
              </section>
            )}
            {journal.map(item => <div className="replay-events-item" key={item.sequence}>
              <time>{new Date(item.time).toLocaleString("ru-RU", {
                timeZone: "UTC", day: "2-digit", month: "2-digit",
                hour: "2-digit", minute: "2-digit",
              })} UTC</time>
              <span>{item.message}</span>
            </div>)}
          </div>
        </aside>
      </div>
      <footer className="replay-footer">
        {simulationGraphPending ? "Ожидаю ▶ Пуск / проверенную историю нового прогона." :
          runLoading ? `${cursor} из ${total} подтверждённых событий · Scanner/Robot продолжают расчёт.` :
          `${cursor} из ${total} событий. Вход на следующем открытии не раскрывает будущую свечу.`}
        Только публичные GET-запросы к истории Bybit; без приватных API, торговли и записи в PAPER.
      </footer>
    </main>
  );
}
