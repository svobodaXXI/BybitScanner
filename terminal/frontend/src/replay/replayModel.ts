/** Read-only contract for SIMULATION event logs, independent of PAPER and order APIs. */
export type ReplayKind = "CANDLE_CLOSED" | "ENTRY_SIGNAL" | "ENTRY_FILLED" | "EXIT_FILLED";
export type ReplayCandle = {
  start_ms: number;
  end_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};
export type ReplayEvent = {
  source: "SIMULATION";
  simulation_run_id: string;
  sequence: number;
  kind: ReplayKind;
  time_ms: number;
  candle?: ReplayCandle;
  trade_id?: string;
  side?: "LONG" | "SHORT";
  price?: number;
  stop?: number;
  take?: number;
  reason?: string;
};
export type ReplayGeometry = {
  kind: "MAIN_1H" | "TARGET_1H" | "REFERENCE_5M";
  side: "BULL" | "BEAR";
  available_at_ms: number;
  from_ms: number;
  to_ms: number;
  from_price: number;
  to_price: number;
  trend_version: number;
  classification: "UNVALIDATED_GEOMETRY_ONLY";
};
export type ReplayDmiPoint = {
  time_ms: number; // Close time, never the opening time of an unfinished candle.
  plus_di: number | null;
  minus_di: number | null;
  adx: number | null;
};
export type ReplayDmi = {
  source: "SIMULATION";
  timeframe: "5m";
  di_length: number;
  adx_smoothing: number;
  points: ReplayDmiPoint[];
};
export type ReplayDocument = {
  source: "SIMULATION";
  simulation_run_id: string;
  events: ReplayEvent[];
  demo?: boolean;
  mode?: "MARKET_ONLY" | "STRATEGY";
  symbol?: string;
  timeframe?: "5m";
  geometry?: ReplayGeometry[];
  dmi_5m?: ReplayDmi;
};
export type VisibleReplay = {
  candles: ReplayCandle[];
  signals: ReplayEvent[];
  fills: ReplayEvent[];
  exits: ReplayEvent[];
  lastTimeMs: number | null;
};

function record(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Ожидается объект JSON");
  }
  return value as Record<string, unknown>;
}
function safeNumber(value: unknown, label: string): number {
  const n = typeof value === "string" && value.trim() ? Number(value) : value;
  if (typeof n !== "number" || !Number.isFinite(n)) {
    throw new Error("Неверное числовое поле: " + label);
  }
  return n;
}
function parseOptionalNumber(value: unknown, label: string): number | undefined {
  return value === undefined ? undefined : safeNumber(value, label);
}
function positiveInteger(value: unknown, label: string): number {
  const n = safeNumber(value, label);
  if (!Number.isSafeInteger(n) || n < 0) throw new Error("Неверный timestamp/порядок: " + label);
  return n;
}
const kinds = new Set<ReplayKind>([
  "CANDLE_CLOSED", "ENTRY_SIGNAL", "ENTRY_FILLED", "EXIT_FILLED",
]);

/** Reject foreign account/report data or any chronology violation; never rewrite input. */
export function parseReplayDocument(input: unknown): ReplayDocument {
  const object = record(input);
  if (object.source !== "SIMULATION") throw new Error("Разрешены только данные SIMULATION");
  const id = object.simulation_run_id;
  if (typeof id !== "string" || !/^[a-zA-Z0-9_-]{1,100}$/.test(id)) {
    throw new Error("Неизвестный идентификатор SIMULATION");
  }
  const mode = object.mode;
  if (mode !== undefined && mode !== "MARKET_ONLY" && mode !== "STRATEGY") {
    throw new Error("Неизвестный режим воспроизведения");
  }
  if (mode === "MARKET_ONLY" && (
    object.market_data_source !== "BYBIT_PUBLIC_KLINE" ||
    typeof object.symbol !== "string" ||
    !/^[A-Z0-9]{3,30}$/.test(object.symbol) ||
    object.timeframe !== "5m" || object.demo === true
  )) {
    throw new Error("Неверная идентичность реальной рыночной истории");
  }
  if (!Array.isArray(object.events) || !object.events.length || object.events.length > 100_000) {
    throw new Error("Ожидается от 1 до 100000 событий");
  }
  let previousTime = -1;
  let previousCandleEnd = -1;
  const events: ReplayEvent[] = object.events.map((raw, index) => {
    const e = record(raw);
    if (e.source !== "SIMULATION" || e.simulation_run_id !== id) {
      throw new Error("Событие принадлежит другому источнику или прогону");
    }
    const sequence = positiveInteger(e.sequence, "sequence");
    if (sequence !== index + 1 || !kinds.has(e.kind as ReplayKind)) {
      throw new Error("Неверная последовательность событий");
    }
    const time_ms = positiveInteger(e.time_ms, "time_ms");
    if (time_ms < previousTime) throw new Error("История событий идёт назад");
    previousTime = time_ms;
    const kind = e.kind as ReplayKind;
    if (mode === "MARKET_ONLY" && kind !== "CANDLE_CLOSED") {
      throw new Error("Рыночный архив не должен содержать сделок или сигналов");
    }
    let candle: ReplayCandle | undefined;
    if (kind === "CANDLE_CLOSED") {
      const c = record(e.candle);
      candle = {
        start_ms: positiveInteger(c.start_ms, "candle.start_ms"),
        end_ms: positiveInteger(c.end_ms, "candle.end_ms"),
        open: safeNumber(c.open, "open"),
        high: safeNumber(c.high, "high"),
        low: safeNumber(c.low, "low"),
        close: safeNumber(c.close, "close"),
        volume: safeNumber(c.volume, "volume"),
      };
      if (
        candle.end_ms !== time_ms || candle.start_ms >= candle.end_ms ||
        candle.start_ms < previousCandleEnd ||
        candle.low <= 0 || candle.volume < 0 ||
        candle.low > Math.min(candle.open, candle.close) ||
        candle.high < Math.max(candle.open, candle.close)
      ) {
        throw new Error("Неверная или перекрывающаяся закрытая свеча");
      }
      previousCandleEnd = candle.end_ms;
    } else if (e.candle !== undefined) {
      throw new Error("Будущая OHLC в событии исполнения недопустима");
    }
    const side = e.side;
    if (side !== undefined && side !== "LONG" && side !== "SHORT") {
      throw new Error("Неверная сторона сделки");
    }
    const trade_id = e.trade_id;
    if (trade_id !== undefined &&
      (typeof trade_id !== "string" || !trade_id.startsWith("SIMULATION:" + id + ":"))) {
      throw new Error("Идентификатор сделки чужого контура");
    }
    if (e.reason !== undefined && typeof e.reason !== "string") {
      throw new Error("Неверная причина выхода");
    }
    return {
      source: "SIMULATION", simulation_run_id: id, kind, sequence, time_ms,
      ...(candle ? { candle } : {}),
      ...(side ? { side } : {}),
      ...(trade_id ? { trade_id } : {}),
      ...(e.reason !== undefined ? { reason: e.reason } : {}),
      ...(e.price !== undefined ? { price: parseOptionalNumber(e.price, "price") } : {}),
      ...(e.stop !== undefined ? { stop: parseOptionalNumber(e.stop, "stop") } : {}),
      ...(e.take !== undefined ? { take: parseOptionalNumber(e.take, "take") } : {}),
    };
  });
  // Geometry is a separate, read-only candidate layer, not order events.
  // Reject any line whose anchors or publication time lie beyond the archive.
  let geometry: ReplayGeometry[] | undefined;
  if (object.geometry !== undefined) {
    if (mode !== "MARKET_ONLY" || !Array.isArray(object.geometry) || object.geometry.length > 100_000) {
      throw new Error("Геометрия разрешена только для рынка SIMULATION");
    }
    let previousAvailable = -1;
    geometry = object.geometry.map((raw) => {
      const item = record(raw);
      const kind = item.kind;
      if (kind !== "MAIN_1H" && kind !== "TARGET_1H" && kind !== "REFERENCE_5M") {
        throw new Error("Неверный вид трендовой линии");
      }
      const side = item.side;
      if (side !== "BULL" && side !== "BEAR" ||
          item.classification !== "UNVALIDATED_GEOMETRY_ONLY") {
        throw new Error("Нельзя выдавать непроверенную геометрию за торговый сигнал");
      }
      const available_at_ms = positiveInteger(item.available_at_ms, "available_at_ms");
      const from_ms = positiveInteger(item.from_ms, "from_ms");
      const to_ms = positiveInteger(item.to_ms, "to_ms");
      const trend_version = positiveInteger(item.trend_version, "trend_version");
      const from_price = safeNumber(item.from_price, "from_price");
      const to_price = safeNumber(item.to_price, "to_price");
      if (
        available_at_ms < previousAvailable ||
        from_ms >= to_ms || to_ms >= available_at_ms ||
        available_at_ms > previousTime ||
        trend_version > available_at_ms ||
        from_price <= 0 || to_price <= 0
      ) {
        throw new Error("Трендовая линия использует неизвестное будущее");
      }
      previousAvailable = available_at_ms;
      return {
        kind, side, available_at_ms, from_ms, to_ms, from_price, to_price,
        trend_version, classification: "UNVALIDATED_GEOMETRY_ONLY" as const,
      };
    });
  }
  // Wilder DMI is a read-only series aligned 1:1 with fully closed
  // market candles. An old JSON archive without DMI remains readable.
  let dmi_5m: ReplayDmi | undefined;
  if (object.dmi_5m !== undefined) {
    if (mode !== "MARKET_ONLY") {
      throw new Error("ADX разрешён только для локальной истории SIMULATION");
    }
    const rawDmi = record(object.dmi_5m);
    if (rawDmi.source !== "SIMULATION" || rawDmi.timeframe !== "5m" ||
        !Array.isArray(rawDmi.points) || rawDmi.points.length !== events.length) {
      throw new Error("ADX не совпадает с последовательностью закрытых свечей");
    }
    const di_length = positiveInteger(rawDmi.di_length, "di_length");
    const adx_smoothing = positiveInteger(rawDmi.adx_smoothing, "adx_smoothing");
    if (di_length < 2 || di_length > 200 || adx_smoothing < 2 || adx_smoothing > 200) {
      throw new Error("Неверные периоды ADX");
    }
    const parseDmiNumber = (value: unknown, field: string): number | null => {
      if (value === null) return null;
      const number = safeNumber(value, field);
      if (number < 0 || number > 100) throw new Error("ADX / DI вне диапазона 0–100");
      return number;
    };
    const points: ReplayDmiPoint[] = rawDmi.points.map((point, index) => {
      const raw = record(point);
      const time_ms = positiveInteger(raw.time_ms, "DMI time_ms");
      if (events[index].kind !== "CANDLE_CLOSED" ||
          time_ms !== events[index].time_ms) {
        throw new Error("ADX использует незакрытую, будущую или чужую свечу");
      }
      const plus_di = parseDmiNumber(raw.plus_di, "+DI");
      const minus_di = parseDmiNumber(raw.minus_di, "-DI");
      const adx = parseDmiNumber(raw.adx, "ADX");
      if ((plus_di === null) !== (minus_di === null) ||
          (index < di_length) !== (plus_di === null) ||
          (index < di_length + adx_smoothing - 1) !== (adx === null)) {
        throw new Error("ADX нарушает последовательность прогрева Wilder");
      }
      return { time_ms, plus_di, minus_di, adx };
    });
    dmi_5m = { source: "SIMULATION", timeframe: "5m", di_length, adx_smoothing, points };
  }
  return {
    source: "SIMULATION", simulation_run_id: id, events, demo: object.demo === true,
    ...(mode ? { mode } : {}),
    ...(mode === "MARKET_ONLY" ? { symbol: object.symbol as string, timeframe: "5m" as const } : {}),
    ...(geometry ? { geometry } : {}),
    ...(dmi_5m ? { dmi_5m } : {}),
  };
}

/** The UI receives ONLY the prefix requested by the virtual-time playhead. */
export function visibleReplay(events: readonly ReplayEvent[], cursor: number): VisibleReplay {
  const shown = events.slice(0, Math.max(0, Math.min(Math.floor(cursor), events.length)));
  const candles: ReplayCandle[] = [];
  const signals: ReplayEvent[] = [];
  const fills: ReplayEvent[] = [];
  const exits: ReplayEvent[] = [];
  for (const event of shown) {
    if (event.kind === "CANDLE_CLOSED" && event.candle) candles.push(event.candle);
    if (event.kind === "ENTRY_SIGNAL") signals.push(event);
    if (event.kind === "ENTRY_FILLED") fills.push(event);
    if (event.kind === "EXIT_FILLED") exits.push(event);
  }
  return {
    candles, signals, fills, exits,
    lastTimeMs: shown.length ? shown[shown.length - 1].time_ms : null,
  };
}

/** Small explicit synthetic fixture; not a market backtest or owner's strategy. */
export function syntheticReplay(): ReplayDocument {
  const id = "SYNTHETIC_DEMO";
  const base = Date.UTC(2026, 10, 4, 0, 0);
  const prices = [100, 101, 99, 102, 103, 104, 106, 107, 105, 104, 102, 101, 103, 105, 106, 105];
  const events: Record<string, unknown>[] = [];
  const push = (kind: ReplayKind, time_ms: number, more: Record<string, unknown> = {}) => {
    events.push({ source: "SIMULATION", simulation_run_id: id, sequence: events.length + 1, kind, time_ms, ...more });
  };
  for (let i = 0; i < prices.length; i++) {
    const start = base + i * 300_000;
    const open = i ? prices[i - 1] : prices[0];
    const close = prices[i];
    if (i === 4) push("ENTRY_FILLED", start, {
      trade_id: "SIMULATION:" + id + ":1", side: "LONG", price: open, stop: 98, take: 108,
    });
    if (i === 8) push("EXIT_FILLED", start + 300_000, {
      trade_id: "SIMULATION:" + id + ":1", side: "LONG", price: 104, reason: "DEMO_EXIT",
    });
    push("CANDLE_CLOSED", start + 300_000, {
      candle: { start_ms: start, end_ms: start + 300_000, open, high: Math.max(open, close) + 1,
        low: Math.min(open, close) - 1, close, volume: 100 + i * 3 },
    });
    if (i === 3) push("ENTRY_SIGNAL", start + 300_000, {
      side: "LONG", price: close, stop: 98, take: 108,
    });
  }
  return parseReplayDocument({ source: "SIMULATION", simulation_run_id: id, events, demo: true });
}

/** Reveal ONLY candidate lines already confirmed at the virtual-time playhead. */
export function visibleGeometry(
  document: ReplayDocument, closedTimeMs: number | null,
): ReplayGeometry[] {
  if (closedTimeMs === null || !document.geometry) return [];
  const current = new Map<ReplayGeometry["kind"], ReplayGeometry>();
  for (const candidate of document.geometry) {
    if (candidate.available_at_ms > closedTimeMs) break;
    current.set(candidate.kind, candidate);
  }
  const main = current.get("MAIN_1H");
  const reference = current.get("REFERENCE_5M");
  if (reference && (!main || reference.trend_version !== main.trend_version)) {
    current.delete("REFERENCE_5M");
  }
  return [...current.values()];
}

/** For MARKET_ONLY, DMI has exactly one observation per completed 5m candle. */
export function visibleDmi(document: ReplayDocument, closedCandles: number): ReplayDmiPoint[] {
  if (document.mode !== "MARKET_ONLY" || !document.dmi_5m) return [];
  return document.dmi_5m.points.slice(
    0, Math.max(0, Math.min(Math.floor(closedCandles), document.dmi_5m.points.length)),
  );
}
