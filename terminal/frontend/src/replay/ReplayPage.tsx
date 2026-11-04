import {
  CandlestickSeries, ColorType, LineSeries, LineStyle, createChart, createSeriesMarkers,
  type IChartApi, type ISeriesApi, type ISeriesMarkersPluginApi,
  type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  parseReplayDocument, syntheticReplay, visibleReplay, visibleGeometry,
  type ReplayCandle, type ReplayDocument, type ReplayEvent, type ReplayGeometry,
} from "./replayModel";
import "./replay.css";

function label(event: ReplayEvent): string {
  switch (event.kind) {
    case "CANDLE_CLOSED": return "Свеча закрылась";
    case "ENTRY_SIGNAL": return "Сигнал " + (event.side ?? "");
    case "ENTRY_FILLED": return "Вход " + (event.side ?? "");
    case "EXIT_FILLED": return "Выход " + (event.reason ?? "");
  }
}
function markerTime(event: ReplayEvent, candles: readonly ReplayCandle[]): number | null {
  if (event.kind === "ENTRY_FILLED") {
    return candles.find((c) => c.start_ms === event.time_ms)?.start_ms ?? null;
  }
  return [...candles].reverse().find((c) => c.end_ms === event.time_ms)?.start_ms ?? null;
}

function ReplayChart({ document, cursor }: { document: ReplayDocument; cursor: number }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markers = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const lines = useRef<Record<ReplayGeometry["kind"], ISeriesApi<"Line">> | null>(null);
  const shown = useMemo(() => visibleReplay(document.events, cursor), [document, cursor]);

  useEffect(() => {
    if (!container.current) return;
    const api = createChart(container.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#121923" }, textColor: "#bcc8d8" },
      grid: { vertLines: { color: "#202d3d" }, horzLines: { color: "#202d3d" } },
      timeScale: { timeVisible: true, secondsVisible: false, rightOffset: 14 },
      crosshair: { mode: 1 },
    });
    const candles = api.addSeries(CandlestickSeries, {
      upColor: "#2fc596", downColor: "#ed6978", wickUpColor: "#2fc596",
      wickDownColor: "#ed6978", borderVisible: false,
    });
    const markerPlugin = createSeriesMarkers(candles, []);
    const chartLines = {
      MAIN_1H: api.addSeries(LineSeries, { color: "#f6dc59", lineWidth: 2, priceLineVisible: false, lastValueVisible: false }),
      TARGET_1H: api.addSeries(LineSeries, { color: "#f6dc59", lineStyle: LineStyle.Dashed, lineWidth: 2, priceLineVisible: false, lastValueVisible: false }),
      REFERENCE_5M: api.addSeries(LineSeries, { color: "#57aaff", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
    };
    lines.current = chartLines;
    chart.current = api;
    series.current = candles;
    markers.current = markerPlugin;
    return () => {
      chart.current = null;
      series.current = null;
      markers.current = null;
      lines.current = null;
      api.remove();
    };
  }, []);

  useEffect(() => {
    const candleSeries = series.current;
    if (!candleSeries) return;
    candleSeries.setData(shown.candles.map((c) => ({
      time: (c.start_ms / 1000) as UTCTimestamp,
      open: c.open, high: c.high, low: c.low, close: c.close,
    })));
    const chartMarkers: SeriesMarker<Time>[] = [];
    for (const event of document.events.slice(0, cursor)) {
      if (event.kind === "CANDLE_CLOSED") continue;
      const time = markerTime(event, shown.candles);
      if (time === null) continue; // Do not draw a future candle for an open fill.
      const isSignal = event.kind === "ENTRY_SIGNAL";
      const isExit = event.kind === "EXIT_FILLED";
      const down = event.side === "SHORT";
      chartMarkers.push({
        time: (time / 1000) as UTCTimestamp,
        position: isExit ? "aboveBar" : down ? "aboveBar" : "belowBar",
        shape: isExit ? "circle" : down ? "arrowDown" : "arrowUp",
        color: isExit ? "#ffcf76" : isSignal ? "#91aafa" : down ? "#ed6978" : "#2fc596",
        text: isSignal ? "Сигнал" : isExit ? (event.reason ?? "Выход") : "Вход",
      });
    }
    chartMarkers.sort((a, b) => Number(a.time) - Number(b.time));
    markers.current?.setMarkers(chartMarkers);
    const allowed = visibleGeometry(document, shown.lastTimeMs);
    const latest = shown.candles.at(-1)?.start_ms;
    for (const [kind, lineSeries] of Object.entries(lines.current ?? {}) as [ReplayGeometry["kind"], ISeriesApi<"Line">][]) {
      const candidate = allowed.find((g) => g.kind === kind);
      if (!candidate || latest === undefined) {
        lineSeries.setData([]);
        continue;
      }
      const points = [
        { time: (candidate.from_ms / 1000) as UTCTimestamp, value: candidate.from_price },
        { time: (candidate.to_ms / 1000) as UTCTimestamp, value: candidate.to_price },
      ];
      if (latest > candidate.to_ms) {
        const projected = candidate.from_price +
          (candidate.to_price - candidate.from_price) *
          (latest - candidate.from_ms) / (candidate.to_ms - candidate.from_ms);
        points.push({ time: (latest / 1000) as UTCTimestamp, value: projected });
      }
      lineSeries.setData(points);
    }
    chart.current?.timeScale().scrollToPosition(14, false);
  }, [shown, document, cursor]);

  return <div className="replay-chart" ref={container} aria-label="Свечной график ускоренной симуляции" />;
}

export function ReplayPage() {
  const [document, setDocument] = useState<ReplayDocument>(() => syntheticReplay());
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(8);
  const [error, setError] = useState<string | null>(null);
  const [fileLabel, setFileLabel] = useState("Синтетический пример");
  const shown = useMemo(() => visibleReplay(document.events, cursor), [document, cursor]);
  const total = document.events.length;
  const progress = Math.round(100 * cursor / total);
  const lastEvents = document.events.slice(Math.max(0, cursor - 8), cursor).reverse();
  const fileInput = useRef<HTMLInputElement>(null);

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
    setPlaying(false);
    try {
      if (file.size > 24 * 1024 * 1024) throw new Error("Файл больше 24 МБ");
      const data: unknown = JSON.parse(await file.text());
      const parsed = parseReplayDocument(data);
      setDocument(parsed);
      setCursor(0);
      setFileLabel(file.name);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось прочитать файл");
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <main className="replay-shell">
      <header className="replay-header">
        <div>
          <h1>Машина времени</h1>
          <p>Локальный визуализатор исторической симуляции · без подключения к торговым счетам</p>
        </div>
        <span className="replay-badge">SIMULATION ONLY</span>
      </header>

      <section className="replay-controls" aria-label="Управление воспроизведением">
        <label className="replay-file">
          Загрузить JSON прогона
          <input ref={fileInput} type="file" accept=".json,application/json"
            onChange={(e) => void loadFile(e.target.files?.[0])} />
        </label>
        <button type="button" onClick={() => {
          setPlaying(false); setCursor(0); setError(null);
          setDocument(syntheticReplay()); setFileLabel("Синтетический пример");
        }}>Пример</button>
        <button type="button" onClick={() => { if (cursor === total) setCursor(0); setPlaying((s) => !s); }}>
          {playing ? "Пауза" : "▶ Пуск"}
        </button>
        <button type="button" onClick={() => { setPlaying(false); setCursor((x) => Math.min(total, x + 1)); }}
          disabled={cursor >= total}>Шаг</button>
        <button type="button" onClick={() => { setPlaying(false); setCursor(0); }}>В начало</button>
        <label className="replay-rate">Скорость {rate} событий/с
          <input type="range" min="1" max="60" value={rate} onChange={(e) => setRate(Number(e.target.value))} />
        </label>
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
        РЕАЛЬНЫЕ СВЕЧИ BYBIT · БЕЗ СДЕЛОК: жёлтые 1H и синие 5m линии — предварительные кандидаты из подтверждённых экстремумов, не проверенная стратегия.
      </p>}
      {document.demo && <p className="replay-note">
        ДЕМО: синтетические свечи и условные события, не реальные сигналы стратегии и не результат Bybit.
      </p>}
      <div className="replay-grid">
        <section className="replay-chart-panel">
          <ReplayChart document={document} cursor={cursor} />
        </section>
        <aside className="replay-events" aria-label="Журнал событий">
          <h2>События</h2>
          {lastEvents.length === 0 && <p>Нажмите «Пуск» или «Шаг».</p>}
          {lastEvents.map((event) => (
            <div className="replay-event" key={event.sequence}>
              <time>{new Date(event.time_ms).toLocaleTimeString("ru-RU", { timeZone: "UTC" })} UTC</time>
              <strong>{label(event)}</strong>
              {event.price !== undefined && <span>{event.price}</span>}
              {event.trade_id && <small>{event.trade_id}</small>}
            </div>
          ))}
        </aside>
      </div>
      <footer className="replay-footer">
        {cursor} из {total} событий. Вход на следующем открытии не раскрывает будущую свечу.
        Никаких запросов к API, торговли или записи в PAPER нет.
      </footer>
    </main>
  );
}
