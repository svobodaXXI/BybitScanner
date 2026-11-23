import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  CandlestickSeries, ColorType, CrosshairMode, LineSeries, createChart,
  type IChartApi, type ISeriesApi, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { editorMoscowCrosshairTime, editorMoscowTickMark } from "../chart/editorMoscowTime";
import { fibonacciPrices } from "../chart/drawingModel";
import { TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR, tradeTrianglePoints } from "../chart/robotTradeMarkers";
import { parseSignalWorkspaceLink } from "../geometryFeedback/signalDeepLink";
import type { ChartTimeframe } from "../marketData/timeframes";

/** Read-only historical evidence in the TERMINAL Statistics view.
 * This component must NEVER import geometry feedback/review drawings.
 */
type Bar = { open_time_ms: number; open: number; high: number; low: number; close: number };
type Anchor = { bar_open_time_ms: number; price: number };
type Boundary = { boundary_id: string; kind: "ray" | "segment" | "horizontal" | "horizontal-ray" | "fibonacci"; anchors: Anchor[] };
type FrozenSignal = { signal_id: string; symbol: string; timeframe: string; bars: Bar[]; boundaries: Boundary[] };
type OriginalEvidence = { snapshot: FrozenSignal; revision: string; intervalMs: number };

type Execution = { at: number; price: number };
type EpisodeMarketScope = {
  episodeId: string; accountId: string; owner: "ROBOT" | "MANUAL"; revision: number;
};
export type OriginalSignalChartProps = {
  candidateId: string | null;
  symbol: string;
  timeframe: string | null;
  pattern: string | null;
  side: "LONG" | "SHORT";
  openedAtMs: number;
  closedAtMs: number;
  executions: readonly Execution[];
  marketScope?: EpisodeMarketScope;
};

function frameMs(frame: string): number | null {
  const key = frame.trim().toUpperCase();
  const aliases: Record<string, number> = {
    "1": 60_000, M1: 60_000, "1M": 60_000,
    "5": 300_000, M5: 300_000, "5M": 300_000,
    "15": 900_000, M15: 900_000, "15M": 900_000,
    "60": 3_600_000, H1: 3_600_000, "1H": 3_600_000,
    "240": 14_400_000, H4: 14_400_000, "4H": 14_400_000,
    D: 86_400_000, D1: 86_400_000, "1D": 86_400_000,
  };
  return aliases[key] ?? null;
}

function asBar(value: unknown): Bar | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  const time = row.open_time_ms;
  if (typeof time !== "number" || !Number.isSafeInteger(time) || time < 0) return null;
  const fields = [row.open, row.high, row.low, row.close];
  if (fields.some(x => typeof x !== "number" || !Number.isFinite(x) || x <= 0)) return null;
  const [open, high, low, close] = fields as number[];
  if (high < Math.max(open, close) || low > Math.min(open, close) || low > high) return null;
  return { open_time_ms: time, open, high, low, close };
}

/** Keep only the immutable snapshot; discard latest_review unconditionally. */
export function parseOriginalTradeSignal(
  value: unknown,
  identity: Pick<OriginalSignalChartProps, "candidateId" | "symbol" | "timeframe" | "pattern" | "openedAtMs">,
): OriginalEvidence | null {
  if (!identity.candidateId || !/^[A-Za-z0-9_.:-]{1,128}$/.test(identity.candidateId)
      || !identity.timeframe || !identity.pattern || !value || typeof value !== "object") return null;
  const response = value as Record<string, unknown>;
  if (response.ok !== true || typeof response.snapshot_revision !== "string"
      || !/^[a-f0-9]{64}$/.test(response.snapshot_revision)
      || !response.snapshot || typeof response.snapshot !== "object") return null;
  if (response.original_pattern != null && response.original_pattern !== identity.pattern) return null;
  const source = response.snapshot as Record<string, unknown>;
  const intervalMs = frameMs(String(source.timeframe ?? ""));
  if (source.signal_id !== identity.candidateId || source.symbol !== identity.symbol
      || !intervalMs || intervalMs !== frameMs(identity.timeframe)
      || !Array.isArray(source.bars) || source.bars.length < 2 || source.bars.length > 2000
      || !Array.isArray(source.boundaries) || !source.boundaries.length
      || source.boundaries.length > 16) return null;
  const bars: Bar[] = [];
  for (const item of source.bars) {
    const bar = asBar(item);
    if (!bar || bar.open_time_ms % intervalMs !== 0
        || (bars.length && bar.open_time_ms <= bars[bars.length - 1].open_time_ms)) return null;
    bars.push(bar);
  }
  // Original source was known before the Robot entry. Reject retrospective snapshots.
  if (bars[bars.length - 1].open_time_ms + intervalMs > identity.openedAtMs) return null;
  const sourceTimes = new Set(bars.map(bar => bar.open_time_ms));
  const seenIds = new Set<string>();
  const boundaries: Boundary[] = [];
  const countByKind: Record<string, number> = {
    ray: 2, segment: 2, horizontal: 1, "horizontal-ray": 1, fibonacci: 2,
  };
  for (const raw of source.boundaries) {
    if (!raw || typeof raw !== "object") return null;
    const row = raw as Record<string, unknown>;
    const id = row.boundary_id, kind = row.kind;
    if (typeof id !== "string" || !id || id.length > 128 || seenIds.has(id)
        || typeof kind !== "string" || !Object.hasOwn(countByKind, kind)
        || !Array.isArray(row.anchors) || row.anchors.length !== countByKind[kind]) return null;
    const anchors: Anchor[] = [];
    for (const item of row.anchors) {
      if (!item || typeof item !== "object") return null;
      const anchor = item as Record<string, unknown>;
      const at = anchor.bar_open_time_ms, price = anchor.price;
      if (typeof at !== "number" || !sourceTimes.has(at)
          || (anchors.length && at <= anchors[anchors.length - 1].bar_open_time_ms)
          || typeof price !== "number" || !Number.isFinite(price) || price <= 0) return null;
      anchors.push({ bar_open_time_ms: at, price });
    }
    seenIds.add(id);
    boundaries.push({ boundary_id: id, kind: kind as Boundary["kind"], anchors });
  }
  return {
    snapshot: { signal_id: identity.candidateId, symbol: identity.symbol,
      timeframe: String(source.timeframe), bars, boundaries },
    revision: response.snapshot_revision, intervalMs,
  };
}

/** The existing Editor API returns ALL candles since the immutable source,
 * not a page. Verify its overlap against already displayed history and append
 * only the new, consecutive 20-candle increment.
 */
export function parseOriginalTradeContinuation(
  raw: unknown, original: OriginalEvidence, lastRequestedMs: number,
  displayed: readonly Bar[] = original.snapshot.bars,
): Bar[] | null {
  if (!raw || typeof raw !== "object") return null;
  const payload = raw as Record<string, unknown>;
  if (payload.ok !== true || payload.signal_id !== original.snapshot.signal_id
      || payload.source_revision !== original.revision
      || !Array.isArray(payload.bars) || !payload.bars.length || payload.bars.length > 1000) return null;
  const source = original.snapshot.bars;
  const lastSource = source[source.length - 1].open_time_ms;
  const elapsed = lastRequestedMs - lastSource;
  if (!Number.isSafeInteger(lastRequestedMs) || lastRequestedMs < lastSource
      || elapsed % original.intervalMs !== 0
      || displayed.length !== source.length + elapsed / original.intervalMs) return null;
  const sameBar = (a: Bar, b: Bar) => a.open_time_ms === b.open_time_ms
    && a.open === b.open && a.high === b.high && a.low === b.low && a.close === b.close;
  if (!source.every((bar, index) => sameBar(bar, displayed[index]))) return null;
  const prior = displayed.slice(source.length);
  const bars: Bar[] = [];
  for (const item of payload.bars) {
    const bar = asBar(item);
    if (!bar || bar.open_time_ms !== lastSource + (bars.length + 1) * original.intervalMs) return null;
    bars.push(bar);
  }
  if (payload.as_of_ms !== bars[bars.length - 1].open_time_ms
      || bars.length <= prior.length || bars.length - prior.length > 20
      || !prior.every((bar, index) => sameBar(bar, bars[index]))) return null;
  return bars.slice(prior.length);
}

/** Secondary timeframe uses genuine Bybit OHLC; never subdivide source M5 to fake M1. */
export function parseOriginalTradeTimeframe(
  raw: unknown, original: OriginalEvidence, interval: string, afterMs: number,
): Bar[] | null {
  if (!raw || typeof raw !== "object" || !frameMs(interval)) return null;
  const payload = raw as Record<string, unknown>;
  const period = frameMs(interval)!;
  if (payload.ok !== true || payload.signal_id !== original.snapshot.signal_id
      || payload.source_revision !== original.revision || payload.interval !== interval
      || !Array.isArray(payload.bars) || !payload.bars.length || payload.bars.length > 20
      || !Number.isSafeInteger(afterMs) || afterMs < 0 || afterMs % period !== 0) return null;
  const bars: Bar[] = [];
  for (const item of payload.bars) {
    const bar = asBar(item);
    if (!bar || bar.open_time_ms !== afterMs + (bars.length + 1) * period) return null;
    bars.push(bar);
  }
  return payload.as_of_ms === bars[bars.length - 1].open_time_ms ? bars : null;
}

const TIMEFRAMES = [
  { id: "D", label: "D1" }, { id: "240", label: "H4" },
  { id: "60", label: "H1" }, { id: "15", label: "M15" },
  { id: "5", label: "M5" }, { id: "1", label: "M1" },
] as const;
function timeframeLabel(frame: string): string {
  return TIMEFRAMES.find(option => frameMs(option.id) === frameMs(frame))?.label ?? frame;
}

const utc = (ms: number) => Math.floor(ms / 1000) as UTCTimestamp;

/** Draw immutable source geometry only over genuine, loaded candle timestamps.
 * Distant anchors must never add whitespace to the chart's time scale.
 * A higher timeframe may have fewer than two supporting candles: omit that
 * projected segment rather than invent candles or distort the source rays.
 */
export function visibleOriginalBoundarySegments(
  boundaries: readonly Boundary[], bars: readonly Bar[],
): Array<{ boundaryId: string; points: Array<{ time: UTCTimestamp; value: number }> }> {
  if (bars.length < 2) return [];
  const first = bars[0].open_time_ms;
  const last = bars[bars.length - 1].open_time_ms;
  const projected: Array<{ boundaryId: string; points: Array<{ time: UTCTimestamp; value: number }> }> = [];
  for (const boundary of boundaries) {
    const a = boundary.anchors[0];
    const b = boundary.anchors[1];
    if (!a) continue;
    if (boundary.kind === "fibonacci") {
      if (!b) continue;
      // Exact original A/B prices and the terminal's native Fib coefficients.
      // Project as horizontal source levels, never as a diagonal price trend.
      const supported = bars.filter(bar => bar.open_time_ms >= b.bar_open_time_ms);
      if (supported.length < 2) continue;
      for (const level of fibonacciPrices(a.price, b.price)) {
        if (!Number.isFinite(level.price) || level.price <= 0) continue;
        projected.push({
          boundaryId: `${boundary.boundary_id}:${level.level}`,
          points: [
            { time: utc(supported[0].open_time_ms), value: level.price },
            { time: utc(supported[supported.length - 1].open_time_ms), value: level.price },
          ],
        });
      }
      continue;
    }
    const start = boundary.kind === "horizontal" ? first : a.bar_open_time_ms;
    const end = boundary.kind === "segment" ? b?.bar_open_time_ms : last;
    if (end == null || end <= start) continue;
    const supported = bars.filter(bar => bar.open_time_ms >= start && bar.open_time_ms <= end);
    if (supported.length < 2) continue;
    const priceAt = (time: number) => b
      ? a.price + (b.price - a.price) * (time - a.bar_open_time_ms)
        / (b.bar_open_time_ms - a.bar_open_time_ms)
      : a.price;
    const begin = supported[0].open_time_ms;
    const finish = supported[supported.length - 1].open_time_ms;
    const values = [priceAt(begin), priceAt(finish)];
    if (values.every(value => Number.isFinite(value) && value > 0)) {
      projected.push({
        boundaryId: boundary.boundary_id,
        points: [
          { time: utc(begin), value: values[0] },
          { time: utc(finish), value: values[1] },
        ],
      });
    }
  }
  return projected;
}

/** Same lightweight-charts engine / Moscow axis as Terminal, but without orders or drawing tools. */
function InteractiveTradeChart({ original, bars, frame, executions, side, showGeometry = true, chartLabel }: {
  original: OriginalEvidence | null; bars: readonly Bar[]; frame: string;
  executions: readonly Execution[]; side: OriginalSignalChartProps["side"];
  showGeometry?: boolean; chartLabel?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick", Time> | null>(null);
  const overlays = useRef<Array<ISeriesApi<"Line", Time>>>([]);
  const previousFrame = useRef<string | null>(null);
  const focusedExecutions = useRef(false);
  const [markerCount, setMarkerCount] = useState(0);
  const [visibleLines, setVisibleLines] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);
  const fillMarkers = useRef<Array<{
    time: UTCTimestamp; price: number; side: "Buy" | "Sell"; color: string;
  }>>([]);
  const [triangles, setTriangles] = useState<Array<{
    x: number; y: number; side: "Buy" | "Sell"; color: string;
  }>>([]);

  const refreshTriangles = () => {
    const chart = api.current, candles = series.current;
    if (!chart || !candles) return;
    setTriangles(fillMarkers.current.flatMap(fill => {
      const x = chart.timeScale().timeToCoordinate(fill.time);
      const y = candles.priceToCoordinate(fill.price);
      return x === null || y === null || !Number.isFinite(x) || !Number.isFinite(y)
        ? [] : [{ x, y, side: fill.side, color: fill.color }];
    }));
  };

  useEffect(() => {
    if (!fullscreen) return;
    closeButton.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullscreen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [fullscreen]);

  useEffect(() => {
    if (!host.current) return;
    const chart = createChart(host.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#10151b" },
        textColor: "#aab9c7", attributionLogo: false,
      },
      localization: { locale: "ru-RU", timeFormatter: editorMoscowCrosshairTime },
      grid: {
        vertLines: { color: "#202830" }, horzLines: { color: "#202830" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        timeVisible: true, secondsVisible: false, rightOffset: 5,
        tickMarkFormatter: editorMoscowTickMark,
      },
      handleScroll: {
        mouseWheel: true, pressedMouseMove: true,
        horzTouchDrag: true, vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true, mouseWheel: true, pinch: true,
      },
    });
    api.current = chart;
    series.current = chart.addSeries(CandlestickSeries, {
      upColor: "#5ac7aa", downColor: "#f0747d",
      wickUpColor: "#5ac7aa", wickDownColor: "#f0747d",
      borderVisible: false,
    });
    const onViewportChange = () => refreshTriangles();
    chart.timeScale().subscribeVisibleLogicalRangeChange(onViewportChange);
    chart.subscribeCrosshairMove(onViewportChange);
    const resize = typeof ResizeObserver === "undefined" ? null
      : new ResizeObserver(onViewportChange);
    if (host.current) resize?.observe(host.current);
    return () => {
      resize?.disconnect();
      chart.unsubscribeCrosshairMove(onViewportChange);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onViewportChange);
      overlays.current = [];
      series.current = null;
      api.current = null;
      previousFrame.current = null;
      focusedExecutions.current = false;
      chart.remove();
    };
  }, [fullscreen]);

  useEffect(() => {
    const chart = api.current, candles = series.current;
    if (!chart || !candles || !bars.length) return;
    const sameFrame = previousFrame.current === frame;
    if (!sameFrame) focusedExecutions.current = false;
    const viewport = sameFrame ? chart.timeScale().getVisibleLogicalRange() : null;
    candles.setData(bars.map(bar => ({
      time: utc(bar.open_time_ms),
      open: bar.open, high: bar.high, low: bar.low, close: bar.close,
    })));
    for (const overlay of overlays.current) chart.removeSeries(overlay);
    overlays.current = [];
    const addOverlay = (points: Array<{ time: UTCTimestamp; value: number }>, color: string) => {
      if (!points.length) return;
      const line = chart.addSeries(LineSeries, {
        color, lineWidth: 2, lineVisible: true,
        pointMarkersVisible: false, lastValueVisible: false,
        priceLineVisible: false,
        // Source projections and execution markers cannot set the candle scale.
        autoscaleInfoProvider: () => null,
      });
      line.setData(points);
      overlays.current.push(line);
    };
    // Only the native source interval has sufficient temporal resolution to
    // represent the original pattern faithfully. Alternate frames are market
    // context, not reconstructed detector geometry.
    const lines = showGeometry && original
      ? visibleOriginalBoundarySegments(original.snapshot.boundaries, bars) : [];
    setVisibleLines(lines.length);
    for (const line of lines) addOverlay(line.points, "#e1b653");
    const candleTimes = new Set(bars.map(bar => bar.open_time_ms));
    const period = frameMs(frame)!;
    const markers: typeof fillMarkers.current = [];
    executions.forEach((fill, index) => {
      const candle = Math.floor(fill.at / period) * period;
      if (!candleTimes.has(candle) || !Number.isFinite(fill.price) || fill.price <= 0) return;
      const opening = index === 0;
      const direction: "Buy" | "Sell" = (side === "LONG") === opening ? "Buy" : "Sell";
      const color = index > 0 && index < executions.length - 1 ? "#f5d68f"
        : direction === "Buy" ? TELEGRAM_BUY_COLOR : TELEGRAM_SELL_COLOR;
      markers.push({ time: utc(candle), price: fill.price, side: direction, color });
    });
    fillMarkers.current = markers;
    const found = markers.length;
    setMarkerCount(found);
    // Focus a proven trade only after its actual execution candles are loaded.
    // Never invent bars, and preserve subsequent owner panning/zoom.
    if (fullscreen) {
      chart.timeScale().fitContent();
    } else if (executions.length > 0 && found === executions.length && !focusedExecutions.current) {
      const firstFill = Math.floor(Math.min(...executions.map(fill => fill.at)) / period) * period;
      const lastFill = Math.floor(Math.max(...executions.map(fill => fill.at)) / period) * period;
      const from = Math.max(bars[0].open_time_ms, firstFill - 8 * period);
      const to = Math.min(bars[bars.length - 1].open_time_ms, lastFill + 8 * period);
      if (from < to) chart.timeScale().setVisibleRange({ from: utc(from), to: utc(to) });
      else chart.timeScale().fitContent();
      focusedExecutions.current = true;
    } else if (viewport) {
      chart.timeScale().setVisibleLogicalRange(viewport);
    } else {
      const visible = bars.slice(-Math.min(bars.length, 80));
      if (visible.length >= 2) chart.timeScale().setVisibleRange({
        from: utc(visible[0].open_time_ms), to: utc(visible[visible.length - 1].open_time_ms),
      });
      else chart.timeScale().fitContent();
    }
    previousFrame.current = frame;
    refreshTriangles();
  }, [original, bars, frame, executions, side, showGeometry, fullscreen]);

  const sourceFrame = original && ({
    "1": "1m", "5": "5m", "15": "15m", "60": "1h", "D": "1d",
  } as Record<string, ChartTimeframe>)[original.snapshot.timeframe];
  const proposedEditorHref = original && sourceFrame
    ? "?" + new URLSearchParams({
      mode: "EDITOR", symbol: original.snapshot.symbol,
      timeframe: sourceFrame, signal_id: original.snapshot.signal_id,
    }).toString()
    : null;
  const editorHref = proposedEditorHref && parseSignalWorkspaceLink(proposedEditorHref)
    ? proposedEditorHref : null;
  const chartBody = (
    <div className="diary-original-signal-plot">
      <div className="diary-trade-chart-host">
        <div ref={host} className="diary-interactive-trade-chart" role="application"
          aria-label={chartLabel ?? "Интерактивный свечной график сделки"} />
        <svg className="diary-chart-triangle-overlay" aria-label="Треугольные маркеры исполнений"
          role="img" aria-hidden="true">
          {triangles.map((mark, index) => <polygon key={index}
            points={tradeTrianglePoints(mark.x, mark.y, mark.side)}
            fill={mark.color} stroke="#10151b" strokeWidth="0.8" />)}
        </svg>
      </div>
      {showGeometry && visibleLines === 0 && <small role="status">
        Исходная геометрия недоступна на загруженных свечах; линии не дорисовываются.
      </small>}
      <div className="diary-trade-chart-controls">
        <div className="diary-trade-chart-actions">
          {!fullscreen && <button type="button" onClick={() => setFullscreen(true)}>
            Весь график
          </button>}
          {editorHref && <a href={editorHref} target="_blank" rel="noopener noreferrer">
            Открыть в Редакторе
          </a>}
        </div>
        <small>Исполнения: {markerCount}/{executions.length}</small>
      </div>
    </div>
  );
  return fullscreen ? createPortal(
    <div className="diary-chart-fullscreen" role="dialog" aria-modal="true"
      aria-label="Полноэкранный график сделки">
      <header>
        <strong>{chartLabel ?? "График сделки"}</strong>
        <button ref={closeButton} type="button" aria-label="Закрыть полноэкранный график"
          onClick={() => setFullscreen(false)}>×</button>
      </header>
      {chartBody}
    </div>, document.body,
  ) : chartBody;
}

type MarketEvidence = { frame: string; bars: Bar[]; complete: boolean };

/** A public-market view is distinct from immutable source geometry. */
export function parseEpisodeMarketContext(raw: unknown, props: OriginalSignalChartProps): MarketEvidence | null {
  const scope = props.marketScope;
  if (!scope || !raw || typeof raw !== "object") return null;
  const payload = raw as Record<string, unknown>;
  if (payload.ok !== true || payload.schema !== "BYBITSCANNER_CLOSED_EPISODE_MARKET_V1"
      || payload.market_source !== "BYBIT_PUBLIC_LINEAR_CLOSED_OHLC"
      || payload.account_id !== scope.accountId || payload.owner !== scope.owner
      || payload.trade_episode_id !== scope.episodeId || payload.source_revision !== scope.revision
      || payload.symbol !== props.symbol || payload.side !== props.side
      || payload.opened_at_ms !== props.openedAtMs || payload.closed_at_ms !== props.closedAtMs
      || typeof payload.interval !== "string"
      || !TIMEFRAMES.some(item => item.id === payload.interval)
      || !Array.isArray(payload.bars) || !payload.bars.length || payload.bars.length > 500) return null;
  const period = frameMs(payload.interval)!;
  const first = Math.max(0, Math.floor(props.openedAtMs / period) * period - 8 * period);
  const exitOpen = Math.floor(props.closedAtMs / period) * period;
  const bars: Bar[] = [];
  for (const entry of payload.bars) {
    const bar = asBar(entry);
    if (!bar || bar.open_time_ms !== first + bars.length * period
        || bar.open_time_ms > exitOpen + 8 * period) return null;
    bars.push(bar);
  }
  const last = bars[bars.length - 1].open_time_ms;
  if (payload.last_open_ms !== last || payload.complete_through_close !== (last >= exitOpen)) return null;
  return { frame: payload.interval, bars, complete: last >= exitOpen };
}

function EpisodeMarketFallback(props: OriginalSignalChartProps) {
  const { marketScope, symbol, side, openedAtMs, closedAtMs, executions } = props;
  const [result, setResult] = useState<MarketEvidence | null>(null);
  const [message, setMessage] = useState("Загружаю свечи сделки…");
  useEffect(() => {
    if (!marketScope) return;
    const controller = new AbortController();
    let active = true;
    setResult(null);
    setMessage("Загружаю свечи сделки…");
    const params = new URLSearchParams({
      account_id: marketScope.accountId, owner: marketScope.owner,
      trade_episode_id: marketScope.episodeId, source_revision: String(marketScope.revision),
    });
    void (async () => {
      try {
        const response = await fetch("/api/diary/episode-candles?" + params.toString(),
          { cache: "no-store", signal: controller.signal });
        if (response.status === 409) {
          if (active) setMessage("История обновилась — откройте Статистику заново.");
          return;
        }
        if (!response.ok) throw new Error("market_history_unavailable");
        const evidence = parseEpisodeMarketContext(await response.json(), props);
        if (!evidence) throw new Error("market_history_mismatch");
        if (!active) return;
        setResult(evidence);
        setMessage(evidence.complete ? "" : "Свеча закрытия сделки ещё не закрыта.");
      } catch {
        if (active) setMessage("Подтверждённые рыночные свечи сделки недоступны.");
      }
    })();
    return () => { active = false; controller.abort(); };
  }, [marketScope?.episodeId, marketScope?.accountId, marketScope?.owner,
      marketScope?.revision, symbol, side, openedAtMs, closedAtMs]);
  return (
    <div className="diary-trade-panel" role="region" aria-label="Рыночный график закрытой сделки">
      {result && <>
        <h4>Свечи Bybit · {timeframeLabel(result.frame)}</h4>
        <InteractiveTradeChart original={null} bars={result.bars} frame={result.frame}
          executions={executions} side={side} showGeometry={false}
          chartLabel="Рыночный свечной график сделки" />
      </>}
      {message && <p className="diary-finrez-basis" role="status">{message}</p>}
    </div>
  );
}

export function OriginalEpisodeSignalChart(props: OriginalSignalChartProps) {
  const { candidateId, symbol, timeframe, pattern, openedAtMs, closedAtMs, executions, side } = props;
  const [original, setOriginal] = useState<OriginalEvidence | null>(null);
  const [archiveUnavailable, setArchiveUnavailable] = useState(false);
  const [barsByFrame, setBarsByFrame] = useState<Record<string, Bar[]>>({});
  const [frame, setFrame] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    activeRequest.current?.abort();
    setOriginal(null);
    setArchiveUnavailable(false);
    setBarsByFrame({});
    setFrame("");
    setLoading(false);
    if (!candidateId || !timeframe || !pattern) {
      setArchiveUnavailable(true);
      setMessage("Исходная геометрия недоступна: нет доказанной связи сделки с исходным сигналом Робота.");
      return;
    }
    const controller = new AbortController();
    activeRequest.current = controller;
    let active = true;
    setMessage("Проверяю архив первоначального сигнала…");
    void (async () => {
      try {
        const response = await fetch("/api/workspace/signal-geometry?signal_id="
          + encodeURIComponent(candidateId), { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("source_unavailable");
        const evidence = parseOriginalTradeSignal(await response.json() as unknown, {
          candidateId, symbol, timeframe, pattern, openedAtMs,
        });
        if (!evidence) throw new Error("source_mismatch");
        if (!active) return;
        setOriginal(evidence);
        setBarsByFrame({ [evidence.snapshot.timeframe]: evidence.snapshot.bars });
        setFrame(evidence.snapshot.timeframe);
        setLoading(true);
        setMessage("Подгружаю реальные закрытые свечи до завершения сделки…");
        const loaded = await loadThroughClose(evidence, evidence.snapshot.timeframe,
          evidence.snapshot.bars, evidence.snapshot.bars[evidence.snapshot.bars.length - 1].open_time_ms);
        if (!active) return;
        setBarsByFrame({ [evidence.snapshot.timeframe]: loaded.bars });
        setMessage(loaded.complete
          ? ""
          : "До завершения сделки загружена только часть проверенных свечей.");
        setLoading(false);
      } catch {
        if (active) {
          setLoading(false);
          setArchiveUnavailable(true);
          setMessage("Исходная геометрия недоступна или не совпадает с сигналом сделки.");
        }
      }
    })();
    return () => { active = false; activeRequest.current?.abort(); controller.abort(); };
  }, [candidateId, symbol, timeframe, pattern, openedAtMs, closedAtMs]);

  async function fetchTradeBars(
    evidence: OriginalEvidence, selected: string, afterMs: number,
    displayed: readonly Bar[] = evidence.snapshot.bars,
  ) {
    const controller = new AbortController();
    activeRequest.current = controller;
    const source = selected === evidence.snapshot.timeframe;
    const url = source
      ? "/api/workspace/signal-geometry/continuation?signal_id="
        + encodeURIComponent(evidence.snapshot.signal_id) + "&after_ms=" + afterMs
      : "/api/workspace/signal-geometry/candles?signal_id="
        + encodeURIComponent(evidence.snapshot.signal_id) + "&interval="
        + encodeURIComponent(selected) + "&after_ms=" + afterMs;
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error("verified_candles_unavailable");
    const raw: unknown = await response.json();
    const rows = source
      ? parseOriginalTradeContinuation(raw, evidence, afterMs, displayed)
      : parseOriginalTradeTimeframe(raw, evidence, selected, afterMs);
    if (!rows) throw new Error("invalid_verified_candles");
    return rows;
  }

  /** At most five authenticated, contiguous 20-candle pages per interaction.
   * Unavailable or inconsistent market history remains visible as a partial window.
   */
  async function loadThroughClose(
    evidence: OriginalEvidence, selected: string, initial: readonly Bar[], afterMs: number,
  ): Promise<{ bars: Bar[]; complete: boolean }> {
    const period = frameMs(selected)!;
    const target = Math.floor(closedAtMs / period) * period;
    let bars = [...initial];
    let last = bars.length ? bars[bars.length - 1].open_time_ms : afterMs;
    for (let page = 0; page < 5 && last < target && bars.length < 2000; page++) {
      try {
        const next = await fetchTradeBars(evidence, selected, last, bars);
        if (!next.length || bars.length + next.length > 2000) break;
        bars = [...bars, ...next];
        last = bars[bars.length - 1].open_time_ms;
      } catch {
        break; // Never fill gaps with interpolated or synthetic candles.
      }
    }
    return { bars, complete: last >= target };
  }

  async function selectFrame(next: string) {
    if (!original || loading || !frameMs(next) || next === frame) return;
    const previous = frame;
    setFrame(next);
    if (barsByFrame[next]) {
      setMessage("");
      return;
    }
    if (next === original.snapshot.timeframe) return;
    setLoading(true);
    setMessage("Загружаю проверенные свечи " + TIMEFRAMES.find(x => x.id === next)?.label + "…");
    const period = frameMs(next)!;
    // The former 20-candle page ended BEFORE the Robot entry: 0/2 executions.
    // Start eight genuine candles before entry, then advance only to the close.
    const firstAllowed = Math.max(0,
      Math.floor(original.snapshot.bars[0].open_time_ms / period) * period - 40 * period);
    const afterMs = Math.max(firstAllowed,
      Math.floor(openedAtMs / period) * period - 8 * period);
    try {
      const loaded = await loadThroughClose(original, next, [], afterMs);
      if (!loaded.bars.length) throw new Error("verified_candles_unavailable");
      setBarsByFrame(prior => ({ ...prior, [next]: loaded.bars }));
      setMessage(loaded.complete
        ? ""
        : "До завершения сделки загружена только часть проверенных свечей.");
    } catch {
      setFrame(previous);
      setMessage("Для этого таймфрейма проверенные свечи пока недоступны.");
    } finally {
      setLoading(false);
    }
  }

  async function addMore() {
    if (!original || loading || !frame) return;
    const existing = barsByFrame[frame] ?? [];
    if (!existing.length || existing.length >= 2000) return;
    const last = existing[existing.length - 1].open_time_ms;
    const lastClosed = (Math.floor(Date.now() / frameMs(frame)!) - 1) * frameMs(frame)!;
    if (last >= lastClosed) {
      setMessage("Новых закрытых свечей пока нет.");
      return;
    }
    setLoading(true);
    setMessage("Загружаю следующие 20 закрытых свечей…");
    try {
      const rows = await fetchTradeBars(original, frame, last, existing);
      if (existing.length + rows.length > 2000) throw new Error("trade_chart_bar_limit");
      setBarsByFrame(prior => {
        const current = prior[frame] ?? [];
        if (!current.length || current[current.length - 1].open_time_ms !== last) return prior;
        return { ...prior, [frame]: [...current, ...rows] };
      });
      setMessage("");
    } catch {
      setMessage("Не удалось получить следующую подтверждённую порцию свечей.");
    } finally {
      setLoading(false);
    }
  }

  const candles = barsByFrame[frame] ?? [];
  const period = frameMs(frame);
  const lastClosed = period ? (Math.floor(Date.now() / period) - 1) * period : 0;
  const canExtend = !!original && !!candles.length && !loading
    && candles.length < 2000 && candles[candles.length - 1].open_time_ms < lastClosed;
  const alternateFrame = !!original && !!frame && frameMs(frame) !== frameMs(original.snapshot.timeframe);
  return (
    <section className="diary-detail-section" aria-label="Исходный сигнал сделки">
      <h3>{archiveUnavailable && props.marketScope
        ? "Свечной график сделки" : "Свечной график · исходный сигнал Робота"}</h3>
      {archiveUnavailable && props.marketScope && <EpisodeMarketFallback {...props} />}
      {original && (
        <div className="diary-trade-timeframes" role="group" aria-label="Таймфрейм сделки">
          {TIMEFRAMES.map(option => <button key={option.id} type="button"
            aria-pressed={frame === option.id} disabled={loading}
            onClick={() => void selectFrame(option.id)}>{option.label}</button>)}
        </div>
      )}
      {original && candles.length > 0 && (
        <div className="diary-trade-panel" role="region"
          aria-label={alternateFrame ? "Рыночный контекст " + timeframeLabel(frame) : "График исходного сигнала"}>
          {alternateFrame && <h4>Рыночный контекст · {timeframeLabel(frame)}</h4>}
          <InteractiveTradeChart original={original} bars={candles} frame={frame}
            executions={executions} side={side}
            showGeometry={!alternateFrame}
            chartLabel={alternateFrame ? "Рыночный контекст " + timeframeLabel(frame) : undefined} />
        </div>
      )}
      {original && (canExtend || loading) && (
        <button className="diary-detail-back" type="button" disabled={!canExtend}
          onClick={() => void addMore()}>
          {loading ? "Загрузка…" : "Показать следующие свечи"}
        </button>
      )}
      {message && <p className="diary-finrez-basis" aria-live="polite">{message}</p>}
    </section>
  );
}
