import { useEffect, useState } from "react";

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

/** Continuations are publicly fetched, closed candles; they never alter source rays. */
export function parseOriginalTradeContinuation(
  raw: unknown, original: OriginalEvidence, lastRequestedMs: number,
): Bar[] | null {
  if (!raw || typeof raw !== "object") return null;
  const payload = raw as Record<string, unknown>;
  if (payload.ok !== true || payload.signal_id !== original.snapshot.signal_id
      || payload.source_revision !== original.revision
      || !Array.isArray(payload.bars) || !payload.bars.length || payload.bars.length > 1000) return null;
  const lastSource = original.snapshot.bars[original.snapshot.bars.length - 1].open_time_ms;
  const bars: Bar[] = [];
  for (const item of payload.bars) {
    const bar = asBar(item);
    if (!bar || bar.open_time_ms !== lastSource + (bars.length + 1) * original.intervalMs) return null;
    bars.push(bar);
  }
  if (payload.as_of_ms !== bars[bars.length - 1].open_time_ms
      || bars[bars.length - 1].open_time_ms <= lastRequestedMs) return null;
  return bars;
}

function Chart({ original, bars, executions, side }: {
  original: OriginalEvidence; bars: readonly Bar[]; executions: readonly Execution[];
  side: OriginalSignalChartProps["side"];
}) {
  const W = 960, H = 320, left = 20, right = 20, top = 16, bottom = 28;
  const first = bars[0].open_time_ms, last = bars[bars.length - 1].open_time_ms;
  const x = (ms: number) => left + (ms - first) / Math.max(original.intervalMs, last - first + original.intervalMs) * (W - left - right);
  const lows = bars.map(b => b.low), highs = bars.map(b => b.high);
  const minimum = Math.min(...lows), maximum = Math.max(...highs);
  const margin = Math.max((maximum - minimum) * 0.06, maximum * 0.0001);
  const lo = minimum - margin, hi = maximum + margin;
  const y = (price: number) => top + (hi - price) / (hi - lo) * (H - top - bottom);
  const upWicks: string[] = [], downWicks: string[] = [];
  const upBodies: string[] = [], downBodies: string[] = [];
  for (const bar of bars) {
    const px = x(bar.open_time_ms);
    const bullish = bar.close >= bar.open;
    (bullish ? upWicks : downWicks).push("M" + px + " " + y(bar.high) + "V" + y(bar.low));
    (bullish ? upBodies : downBodies).push("M" + px + " " + y(bar.open) + "V" + y(bar.close));
  }
  const width = Math.max(1, Math.min(5, (W - left - right) / bars.length * 0.68));
  const lines = original.snapshot.boundaries.map(boundary => {
    const a = boundary.anchors[0], b = boundary.anchors[1];
    const to = boundary.kind === "horizontal" || boundary.kind === "horizontal-ray" || boundary.kind === "ray"
      ? last : b?.bar_open_time_ms ?? last;
    const at = boundary.kind === "horizontal" ? first : a.bar_open_time_ms;
    const priceAt = (ms: number) => b
      ? a.price + (b.price - a.price) * (ms - a.bar_open_time_ms) / (b.bar_open_time_ms - a.bar_open_time_ms)
      : a.price;
    return {
      id: boundary.boundary_id,
      path: "M" + x(at) + " " + y(priceAt(at)) + "L" + x(to) + " " + y(priceAt(to)),
    };
  });
  const markers = executions.map((fill, index) => {
    const candle = bars.find(b => b.open_time_ms <= fill.at
      && fill.at < b.open_time_ms + original.intervalMs);
    if (!candle || !Number.isFinite(fill.price) || fill.price < candle.low || fill.price > candle.high)
      return null;
    const opening = index === 0;
    const color = opening ? (side === "SHORT" ? "#f0747d" : "#5ac7aa")
      : index === executions.length - 1 ? (side === "SHORT" ? "#5ac7aa" : "#f0747d") : "#f5d68f";
    return { id: index, x: x(candle.open_time_ms), y: y(fill.price), price: fill.price,
      at: fill.at, color, label: opening ? "Первое исполнение" :
        index === executions.length - 1 ? "Последнее исполнение" : "Исполнение" };
  }).filter((m): m is NonNullable<typeof m> => m !== null);
  return (
    <div className="diary-original-signal-plot">
      <svg viewBox="0 0 960 320" role="img" aria-label="Закрытые свечи и исходные линии сигнала Робота">
        <rect x={0} y={0} width={W} height={H} fill="#10151b" />
        <path d={upWicks.join(" ")} fill="none" stroke="#5ac7aa" strokeWidth={1} />
        <path d={downWicks.join(" ")} fill="none" stroke="#f0747d" strokeWidth={1} />
        <path d={upBodies.join(" ")} fill="none" stroke="#5ac7aa" strokeWidth={width} />
        <path d={downBodies.join(" ")} fill="none" stroke="#f0747d" strokeWidth={width} />
        {lines.map(line => <path key={line.id} d={line.path}
          stroke="#e1b653" strokeWidth={2} fill="none" />)}
        {markers.map(m => <circle key={m.id} cx={m.x} cy={m.y} r={4.5}
          stroke={m.color} strokeWidth={2} fill="#10151b">
          <title>{m.label + ": " + m.price + " · " + new Date(m.at).toISOString()}</title>
        </circle>)}
        <text x={left} y={H - 5} fontSize={11} fill="#aab9c7">
          {new Date(first).toISOString().slice(0, 16).replace("T", " ") + " UTC"}
        </text>
        <text x={W - right} y={H - 5} fontSize={11} fill="#aab9c7" textAnchor="end">
          {new Date(last + original.intervalMs).toISOString().slice(0, 16).replace("T", " ") + " UTC"}
        </text>
      </svg>
      <small>Жёлтые линии: только оригинальные архивные якоря. Кружки: фактические исполнения в подтверждённых свечах ({markers.length}/{executions.length}).</small>
    </div>
  );
}

export function OriginalEpisodeSignalChart(props: OriginalSignalChartProps) {
  const { candidateId, symbol, timeframe, pattern, openedAtMs, closedAtMs, executions, side } = props;
  const [original, setOriginal] = useState<OriginalEvidence | null>(null);
  const [candles, setCandles] = useState<Bar[]>([]);
  const [message, setMessage] = useState("");
  useEffect(() => {
    setOriginal(null);
    setCandles([]);
    if (!candidateId || !timeframe || !pattern) {
      setMessage("Исходная геометрия недоступна: нет доказанной связи сделки с исходным сигналом Робота.");
      return;
    }
    let active = true;
    const controller = new AbortController();
    const base = "/api/workspace/signal-geometry?signal_id=" + encodeURIComponent(candidateId);
    setMessage("Проверяю архив первоначального сигнала…");
    void (async () => {
      try {
        const response = await fetch(base, { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("original_unavailable");
        const evidence = parseOriginalTradeSignal(await response.json() as unknown, {
          candidateId, symbol, timeframe, pattern, openedAtMs,
        });
        if (!evidence) throw new Error("original_identity_mismatch");
        if (!active) return;
        setOriginal(evidence);
        setCandles(evidence.snapshot.bars);
        const originalLast = evidence.snapshot.bars[evidence.snapshot.bars.length - 1].open_time_ms;
        let last = originalLast;
        const needed = Math.floor(closedAtMs / evidence.intervalMs) * evidence.intervalMs;
        setMessage("Исходный сигнал подтверждён; получаю закрытые свечи после сигнала…");
        // Existing owner-initiated public continuation fetches 20 closed bars per request.
        // Bounded retries: never flood the backend, never invent a missing interval.
        for (let n = 0; n < 20 && last < needed; n++) {
          const url = "/api/workspace/signal-geometry/continuation?signal_id="
            + encodeURIComponent(candidateId) + "&after_ms=" + last;
          const next = await fetch(url, { cache: "no-store", signal: controller.signal });
          if (!next.ok) throw new Error("market_extension_unavailable");
          const extension = parseOriginalTradeContinuation(
            await next.json() as unknown, evidence, last,
          );
          if (!extension) throw new Error("invalid_market_extension");
          last = extension[extension.length - 1].open_time_ms;
          if (!active) return;
          setCandles([...evidence.snapshot.bars, ...extension.filter(bar => bar.open_time_ms <= needed)]);
        }
        if (active) setMessage(last >= needed
          ? "Исходная геометрия и публичные закрытые свечи до выхода получены."
          : "Период сделки длиннее доступного окна. Отображён только подтверждённый участок.");
      } catch (error) {
        if (!active) return;
        setMessage(error instanceof Error && error.message === "original_identity_mismatch"
          ? "Исходная геометрия недоступна: архив не совпадает с точным сигналом и временем сделки."
          : originalLastMessage());
      }
    })();
    function originalLastMessage() {
      return "Исходная геометрия или дальнейшие закрытые свечи недоступны. Не подставляем исправления из Редактора и не выдумываем историю.";
    }
    return () => { active = false; controller.abort(); };
  }, [candidateId, symbol, timeframe, pattern, openedAtMs, closedAtMs]);
  return (
    <section className="diary-detail-section" aria-label="Исходный сигнал сделки">
      <h3>Свечной график · исходный сигнал Робота</h3>
      {original && candles.length > 0 && <Chart original={original} bars={candles}
        executions={executions} side={side} />}
      <p className="diary-finrez-basis" aria-live="polite">{message}</p>
      <small>Только неизменяемый архив сигнала. Геометрия из Редактора не используется; это не воспроизведение решений Robot.</small>
    </section>
  );
}
