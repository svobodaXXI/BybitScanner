import {
  CandlestickSeries, ColorType, LineSeries, LineStyle, createChart,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  parseReplayDocument, syntheticReplay, visibleReplay, visibleGeometry, visibleDmi,
  type ReplayCandle, type ReplayDocument, type ReplayEvent, type ReplayGeometry,
} from "./replayModel";
import { visibleExecutionMarkers, TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR } from "./executionMarkers";
import "./replay.css";

function label(event: ReplayEvent): string {
  switch (event.kind) {
    case "CANDLE_CLOSED": return "Свеча закрылась";
    case "ENTRY_SIGNAL": return "Сигнал " + (event.side ?? "");
    case "ENTRY_FILLED": return "Вход " + (event.side ?? "");
    case "EXIT_FILLED": return "Выход " + (event.reason ?? "");
  }
}
  function ReplayChart({ document, cursor }: { document: ReplayDocument; cursor: number }) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const executionCanvas = useRef<HTMLCanvasElement>(null);
  const renderExecutions = useRef<() => void>(() => {});
  const lines = useRef<Record<ReplayGeometry["kind"], ISeriesApi<"Line">> | null>(null);
  const indicators = useRef<Record<"PLUS" | "MINUS" | "ADX" | "LEVEL", ISeriesApi<"Line">> | null>(null);
  const shown = useMemo(() => visibleReplay(document.events, cursor), [document, cursor]);
  const observedDmi = useMemo(() => visibleDmi(document, shown.candles.length), [document, shown.candles.length]);
  const latestDmi = observedDmi.at(-1);
  const dmiValue = (value: number | null | undefined) => value == null ? "—" : value.toFixed(1);

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
    const chartLines = {
      MAIN_1H: api.addSeries(LineSeries, { color: "#f6dc59", lineWidth: 2, priceLineVisible: false, lastValueVisible: false }),
      TARGET_1H: api.addSeries(LineSeries, { color: "#f6dc59", lineStyle: LineStyle.Dashed, lineWidth: 2, priceLineVisible: false, lastValueVisible: false }),
      REFERENCE_5M: api.addSeries(LineSeries, { color: "#57aaff", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }),
    };
    lines.current = chartLines;
    // Lightweight Charts v5: a second pane shares the exact candle time axis
    // and crosshair. Unlike an overlay, ADX uses its own 0..100 value scale.
    const paneOptions = {
      lineWidth: 2 as const, priceLineVisible: false, lastValueVisible: true,
      priceFormat: { type: "price" as const, precision: 1, minMove: 0.1 },
    };
    const indicatorLines = {
      PLUS: api.addSeries(LineSeries, { ...paneOptions, title: "+DI", color: "#25c776" }, 1),
      MINUS: api.addSeries(LineSeries, { ...paneOptions, title: "-DI", color: "#f16a72" }, 1),
      ADX: api.addSeries(LineSeries, { ...paneOptions, title: "ADX", color: "#60a5fa" }, 1),
      LEVEL: api.addSeries(LineSeries, {
        ...paneOptions, title: "20", color: "#8595ab", lineWidth: 1,
        lineStyle: LineStyle.Dashed, lastValueVisible: false,
      }, 1),
    };
    api.panes()[1]?.setHeight(185);
    indicators.current = indicatorLines;
    chart.current = api;
    series.current = candles;
    // Repaint true-price execution triangles when chart scroll/zoom/resize moves.
    const refresh = () => renderExecutions.current();
    api.timeScale().subscribeVisibleLogicalRangeChange(refresh);
    api.subscribeCrosshairMove(refresh);
    const resize = new ResizeObserver(refresh);
    resize.observe(container.current);
    return () => {
      resize.disconnect();
      api.unsubscribeCrosshairMove(refresh);
      api.timeScale().unsubscribeVisibleLogicalRangeChange(refresh);
      chart.current = null;
      series.current = null;
       lines.current = null;
      indicators.current = null;
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
     const dmiSeries = indicators.current;
    if (dmiSeries) {
      const linePoints = (key: "plus_di" | "minus_di" | "adx") => {
        const values: { time: UTCTimestamp; value: number }[] = [];
        observedDmi.forEach((sample, index) => {
          const value = sample[key];
          if (value !== null) {
            values.push({
              // Chart bar's X is its START, while the sample becomes known
              // only at the CLOSE. We reveal it only after that close event.
              time: (shown.candles[index].start_ms / 1000) as UTCTimestamp,
              value,
            });
          }
        });
        return values;
      };
      dmiSeries.PLUS.setData(linePoints("plus_di"));
      dmiSeries.MINUS.setData(linePoints("minus_di"));
      dmiSeries.ADX.setData(linePoints("adx"));
      const first = shown.candles[0];
      const last = shown.candles.at(-1);
      dmiSeries.LEVEL.setData(first && last ? [
        { time: (first.start_ms / 1000) as UTCTimestamp, value: 20 },
        ...(last.start_ms !== first.start_ms
          ? [{ time: (last.start_ms / 1000) as UTCTimestamp, value: 20 }]
          : []),
      ] : []);
    }
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
      const fills = visibleExecutionMarkers(document.events.slice(0, cursor), shown.candles);
      let rendered = 0;
      for (const fill of fills) {
        const x = api.timeScale().timeToCoordinate((fill.candle_start_ms / 1000) as UTCTimestamp);
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
      canvas.dataset.visibleFills = String(rendered);
    };
    chart.current?.timeScale().scrollToPosition(14, false);
    renderExecutions.current();
    // Chart recalculates pixel coordinates after updating series/timescale.
    const redrawId = requestAnimationFrame(() => renderExecutions.current());
    return () => cancelAnimationFrame(redrawId);
  }, [shown, document, cursor, observedDmi]);

  return (
    <div className="replay-chart-shell">
      <div className="replay-chart-frame">
        <div className="replay-chart" ref={container}
          aria-label="Свечной график и нижняя панель ADX DMI" />
        <canvas ref={executionCanvas} className="replay-execution-overlay"
          aria-hidden="true" data-visible-fills="0" />
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
    historyRequest.current?.abort();
    historyRequest.current = null;
    setHistoryLoading(false);
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

  async function loadLocalHistory() {
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
          <p>Локальный визуализатор исторической симуляции · без подключения к торговым счетам</p>
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
          historyRequest.current?.abort(); historyRequest.current = null;
          setHistoryLoading(false); setPlaying(false); setCursor(0); setError(null);
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
        Только публичные GET-запросы к истории Bybit; без приватных API, торговли и записи в PAPER.
      </footer>
    </main>
  );
}
