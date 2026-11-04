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
export type ReplayDocument = {
  source: "SIMULATION";
  simulation_run_id: string;
  events: ReplayEvent[];
  demo?: boolean;
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
  return { source: "SIMULATION", simulation_run_id: id, events, demo: object.demo === true };
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
