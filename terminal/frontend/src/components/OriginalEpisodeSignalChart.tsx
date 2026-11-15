import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, LineSeries, createChart,
  type IChartApi, type ISeriesApi, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { editorMoscowCrosshairTime, editorMoscowTickMark } from "../chart/editorMoscowTime";

/** Read-only historical evidence in the TERMINAL Statistics view.
 * This component must NEVER import geometry feedback/review drawings.
 */
type Bar = { open_time_ms: number; open: number; high: number; low: number; close: number };
type Anchor = { bar_open_time_ms: number; price: number };
type Boundary = { boundary_id: string; kind: "ray" | "segment" | "horizontal" | "horizontal-ray"; anchors: Anchor[] };
type FrozenSignal = { signal_id: string; symbol: string; timeframe: string; bars: Bar[]; boundaries: Boundary[] };
type OriginalEvidence = { snapshot: FrozenSignal; revision: string; intervalMs: number };

type Execution = { at: number; price: number };
export type OriginalSignalChartProps = {
  candidateId: string | null;
  symbol: string;
  timeframe: string | null;
  pattern: string | null;
  side: "LONG" | "SHORT";
  openedAtMs: number;
  closedAtMs: number;
  executions: readonly Execution[];
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
    ray: 2, segment: 2, horizontal: 1, "horizontal-ray": 1,
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
  original: OriginalEvidence; bars: readonly Bar[]; frame: string;
  executions: readonly Execution[]; side: OriginalSignalChartProps["side"];
  showGeometry?: boolean; chartLabel?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick", Time> | null>(null);
  const overlays = useRef<Array<ISeriesApi<"Line", Time>>>([]);
  const previousFrame = useRef<string | null>(null);
  const [markerCount, setMarkerCount] = useState(0);
  const [visibleLines, setVisibleLines] = useState(0);

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
    return () => {
      overlays.current = [];
      series.current = null;
      api.current = null;
      previousFrame.current = null;
      chart.remove();
    };
  }, []);

  useEffect(() => {
    const chart = api.current, candles = series.current;
    if (!chart || !candles || !bars.length) return;
    const sameFrame = previousFrame.current === frame;
    const viewport = sameFrame ? chart.timeScale().getVisibleLogicalRange() : null;
    candles.setData(bars.map(bar => ({
      time: utc(bar.open_time_ms),
      open: bar.open, high: bar.high, low: bar.low, close: bar.close,
    })));
    for (const overlay of overlays.current) chart.removeSeries(overlay);
    overlays.current = [];
    const addOverlay = (points: Array<{ time: UTCTimestamp; value: number }>, color: string, marker = false) => {
      if (!points.length) return;
      const line = chart.addSeries(LineSeries, {
        color, lineWidth: marker ? 1 : 2, lineVisible: !marker,
        pointMarkersVisible: marker, pointMarkersRadius: marker ? 5 : 0,
        crosshairMarkerVisible: marker, lastValueVisible: false,
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
    const lines = showGeometry
      ? visibleOriginalBoundarySegments(original.snapshot.boundaries, bars) : [];
    setVisibleLines(lines.length);
    for (const line of lines) addOverlay(line.points, "#e1b653");
    const candleTimes = new Set(bars.map(bar => bar.open_time_ms));
    const period = frameMs(frame)!;
    let found = 0;
    executions.forEach((fill, index) => {
      const candle = Math.floor(fill.at / period) * period;
      if (!candleTimes.has(candle) || !Number.isFinite(fill.price) || fill.price <= 0) return;
      const opening = index === 0;
      const color = opening ? (side === "SHORT" ? "#f0747d" : "#5ac7aa")
        : index === executions.length - 1 ? (side === "SHORT" ? "#5ac7aa" : "#f0747d")
          : "#f5d68f";
      addOverlay([{ time: utc(candle), value: fill.price }], color, true);
      found++;
    });
    setMarkerCount(found);
    if (viewport) {
      chart.timeScale().setVisibleLogicalRange(viewport);
    } else {
      const visible = bars.slice(-Math.min(bars.length, 80));
      if (visible.length >= 2) chart.timeScale().setVisibleRange({
        from: utc(visible[0].open_time_ms), to: utc(visible[visible.length - 1].open_time_ms),
      });
      else chart.timeScale().fitContent();
    }
    previousFrame.current = frame;
  }, [original, bars, frame, executions, side, showGeometry]);

  return (
    <div className="diary-original-signal-plot">
      <div ref={host} className="diary-interactive-trade-chart" role="application"
        aria-label={chartLabel ?? "Интерактивный свечной график сделки"} />
      {showGeometry && visibleLines === 0 && <small role="status">
        Исходная геометрия недоступна на загруженных свечах; линии не дорисовываются.
      </small>}
      <div className="diary-trade-chart-controls">
        <span>{showGeometry ? "Жёлтые линии: исходная геометрия · МСК" : "Закрытые свечи выбранного ТФ · МСК"}</span>
        <button type="button" onClick={() => api.current?.timeScale().fitContent()}>
          Весь график
        </button>
      </div>
      <small>Фактические исполнения на загруженных свечах: {markerCount}/{executions.length}.
        Удерживайте палец для перекрестия; двигайте и масштабируйте график двумя пальцами.</small>
    </div>
  );
}

export function OriginalEpisodeSignalChart(props: OriginalSignalChartProps) {
  const { candidateId, symbol, timeframe, pattern, openedAtMs, executions, side } = props;
  const [original, setOriginal] = useState<OriginalEvidence | null>(null);
  const [barsByFrame, setBarsByFrame] = useState<Record<string, Bar[]>>({});
  const [frame, setFrame] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    activeRequest.current?.abort();
    setOriginal(null);
    setBarsByFrame({});
    setFrame("");
    setLoading(false);
    if (!candidateId || !timeframe || !pattern) {
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
        setMessage("Исходный сигнал подтверждён. Следующие 20 закрытых свечей — по кнопке.");
      } catch {
        if (active) setMessage("Исходная геометрия недоступна или не совпадает с сигналом сделки.");
      }
    })();
    return () => { active = false; controller.abort(); };
  }, [candidateId, symbol, timeframe, pattern, openedAtMs]);

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

  async function selectFrame(next: string) {
    if (!original || loading || !frameMs(next) || next === frame) return;
    const previous = frame;
    setFrame(next);
    if (barsByFrame[next]) {
      setMessage("Показаны ранее загруженные закрытые свечи.");
      return;
    }
    if (next === original.snapshot.timeframe) return;
    setLoading(true);
    setMessage("Загружаю проверенные свечи " + TIMEFRAMES.find(x => x.id === next)?.label + "…");
    const period = frameMs(next)!;
    const sourceLastClose = original.snapshot.bars[original.snapshot.bars.length - 1].open_time_ms
      + original.intervalMs;
    const lastBeforeEntry = Math.floor(sourceLastClose / period) * period - period;
    const afterMs = lastBeforeEntry - 20 * period;
    try {
      const rows = await fetchTradeBars(original, next, afterMs);
      setBarsByFrame(prior => ({ ...prior, [next]: rows }));
      setMessage("Закрытые свечи получены; для следующих 20 нажмите кнопку.");
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
      setMessage("Следующие закрытые свечи добавлены.");
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
      <h3>Свечной график · исходный сигнал Робота</h3>
      {original && (
        <div className="diary-trade-timeframes" role="group" aria-label="Таймфрейм сделки">
          {TIMEFRAMES.map(option => <button key={option.id} type="button"
            aria-pressed={frame === option.id} disabled={loading}
            onClick={() => void selectFrame(option.id)}>{option.label}</button>)}
        </div>
      )}
      {original && alternateFrame && <p className="diary-finrez-basis">
        Выбранный {timeframeLabel(frame)} показывает реальные свечи для контекста.
        Исходная фигура сохраняется отдельно на {timeframeLabel(original.snapshot.timeframe)}:
        перенос её линий на другой масштаб изменил бы смысл исходных координат.
      </p>}
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
      {original && alternateFrame && (
        <div className="diary-trade-panel" role="region" aria-label="Исходная фигура сделки">
          <h4>Исходная фигура · {timeframeLabel(original.snapshot.timeframe)}</h4>
          <InteractiveTradeChart original={original} bars={original.snapshot.bars}
            frame={original.snapshot.timeframe} executions={executions} side={side}
            chartLabel="Исходный график сигнала" />
        </div>
      )}
      {original && (
        <button className="diary-detail-back" type="button" disabled={!canExtend}
          onClick={() => void addMore()}>
          {loading ? "Загрузка…" : "Показать следующие свечи"}
        </button>
      )}
      <p className="diary-finrez-basis" aria-live="polite">{message}</p>
      <small>Только неизменяемый архив сигнала и настоящие закрытые свечи.
        Изменения Редактора и неподтверждённые исполнения не подставляются.</small>
    </section>
  );
}
