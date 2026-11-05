/** Read-only contract for SIMULATION event logs, independent of PAPER and order APIs. */
import syntheticDmiFixture from "./syntheticDmiFixture.json";
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
export type ReplayObservation = {
  kind: "MAIN_1H_TOUCH" | "MAIN_1H_REACTION";
  side: "BULL" | "BEAR";
  time_ms: number; // Released only when the M5 observation candle closes.
  touch_time_ms?: number; // Required for a follow-through after a prior touch.
  price: number;
  line_price: number;
  trend_version: number;
  classification: "UNVALIDATED_GEOMETRY_ONLY";
};
export type H017BlueRiskPreview = {
  source: "SIMULATION";
  kind: "BLUE_5M_OPEN";
  classification: "UNVALIDATED_GEOMETRY_ONLY";
  time_ms: number; // Released only after this 5m candle closes.
  open_ms: number;
  trend_version: number;
  blue_available_at_ms: number;
  side: "LONG" | "SHORT";
  entry_price: number;
  blue_price: number;
  target_price: number;
  risk_status: "RISK_PASS" | "RISK_BELOW_1R";
  stop_price?: number;
  quantity?: number;
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
  observations?: ReplayObservation[];
  h017_blue_risk_previews?: H017BlueRiskPreview[];
  geometry_warmup_hours?: number;
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
  const geometry_warmup_hours = object.geometry_warmup_hours === undefined
    ? undefined : positiveInteger(object.geometry_warmup_hours, "geometry_warmup_hours");
  if (geometry_warmup_hours !== undefined && (mode !== "MARKET_ONLY" || geometry_warmup_hours > 72)) {
    throw new Error("Неверная предыстория геометрии");
  }
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
  // H-017: evaluate known blue-line OPENs, but never turn previews into fills.
  let h017_blue_risk_previews: H017BlueRiskPreview[] | undefined;
  if (object.h017_blue_risk_previews !== undefined) {
    if (mode !== "MARKET_ONLY" || !Array.isArray(object.h017_blue_risk_previews) ||
        object.h017_blue_risk_previews.length > 100_000) {
      throw new Error("H-017 допускается только для рыночной SIMULATION");
    }
    const closedByStart = new Map(events.filter(e => e.kind === "CANDLE_CLOSED")
      .map(e => [e.candle!.start_ms, e.candle!] as const));
    const active = new Map<ReplayGeometry["kind"], ReplayGeometry>();
    let lineIndex = 0;
    let previousOpen = -1;
    const projected = (line: ReplayGeometry, at: number) =>
      line.from_price + (line.to_price - line.from_price) *
        (at - line.from_ms) / (line.to_ms - line.from_ms);
    const closeEnough = (x: number, y: number) =>
      Math.abs(x - y) <= (1 + Math.abs(y)) * 1e-9; // Decimal -> JS tolerance, not a market filter
    h017_blue_risk_previews = object.h017_blue_risk_previews.map(raw => {
      const item = record(raw);
      const open_ms = positiveInteger(item.open_ms, "H-017 open_ms");
      const time_ms = positiveInteger(item.time_ms, "H-017 time_ms");
      const trend_version = positiveInteger(item.trend_version, "H-017 trend_version");
      const blue_available_at_ms = positiveInteger(item.blue_available_at_ms, "H-017 blue available");
      const entry_price = safeNumber(item.entry_price, "H-017 entry");
      const blue_price = safeNumber(item.blue_price, "H-017 reference");
      const target_price = safeNumber(item.target_price, "H-017 target");
      const side = item.side;
      const risk_status = item.risk_status;
      const candle = closedByStart.get(open_ms);
      if (item.source !== "SIMULATION" || item.kind !== "BLUE_5M_OPEN" ||
          item.classification !== "UNVALIDATED_GEOMETRY_ONLY" ||
          (side !== "LONG" && side !== "SHORT") ||
          (risk_status !== "RISK_PASS" && risk_status !== "RISK_BELOW_1R") ||
          !candle || candle.end_ms !== time_ms || open_ms <= previousOpen ||
          time_ms > previousTime || entry_price <= 0 || blue_price <= 0 ||
          target_price <= 0 || blue_available_at_ms > open_ms || trend_version > open_ms ||
          !closeEnough(entry_price, candle.open) || item.trade_id !== undefined) {
        throw new Error("Недостоверный H-017 кандидат или будущая свеча");
      }
      previousOpen = open_ms;
      while (geometry && lineIndex < geometry.length &&
          geometry[lineIndex].available_at_ms <= open_ms) {
        const line = geometry[lineIndex++];
        active.set(line.kind, line);
      }
      const blue = active.get("REFERENCE_5M");
      const main = active.get("MAIN_1H");
      const target = active.get("TARGET_1H");
      const trendSide = side === "LONG" ? "BULL" : "BEAR";
      if (!blue || !main || !target || blue.side !== trendSide ||
          main.side !== trendSide || target.side !== trendSide ||
          main.trend_version !== trend_version ||
          target.trend_version !== trend_version ||
          blue.trend_version !== trend_version ||
          !closeEnough(projected(blue, open_ms), blue_price) ||
          !closeEnough(projected(target, open_ms), target_price) ||
          (side === "LONG" ? entry_price <= blue_price : entry_price >= blue_price)) {
        throw new Error("Кандидат H-017 не соответствует известной геометрии");
      }
      const reward = side === "LONG" ? target_price - entry_price : entry_price - target_price;
      const risk = entry_price * 0.007;
      const qualifies = reward + 1e-9 * (1 + entry_price) >= risk;
      if ((risk_status === "RISK_PASS") !== qualifies) {
        throw new Error("Неверная проверка H-017 по 1:1");
      }
      if (risk_status === "RISK_PASS") {
        const stop_price = safeNumber(item.stop_price, "H-017 stop");
        const quantity = safeNumber(item.quantity, "H-017 quantity");
        const fixedStop = entry_price * (side === "LONG" ? 0.993 : 1.007);
        if (!closeEnough(stop_price, fixedStop) || quantity <= 0 ||
            quantity > 10 / entry_price + 1e-9) {
          throw new Error("Неверная проверка H-017 0,7% или 10 USDT");
        }
        return { source: "SIMULATION", kind: "BLUE_5M_OPEN",
          classification: "UNVALIDATED_GEOMETRY_ONLY" as const,
          time_ms, open_ms, trend_version, blue_available_at_ms, side,
          entry_price, blue_price, target_price, risk_status, stop_price, quantity };
      }
      if (item.stop_price !== undefined || item.quantity !== undefined) {
        throw new Error("Отклонённый H-017 кандидат не может быть исполнением");
      }
      return { source: "SIMULATION", kind: "BLUE_5M_OPEN",
        classification: "UNVALIDATED_GEOMETRY_ONLY" as const,
        time_ms, open_ms, trend_version, blue_available_at_ms, side,
        entry_price, blue_price, target_price, risk_status };
    });
  }
  // Separate research-only OHLC touch/reaction observations; NEVER trade events.
  let observations: ReplayObservation[] | undefined;
  if (object.observations !== undefined) {
    if (mode !== "MARKET_ONLY" || !Array.isArray(object.observations) ||
        object.observations.length > 100_000) {
      throw new Error("Наблюдения трендовой разрешены только в рыночной SIMULATION");
    }
    const closedBars = new Map(events.filter(e => e.kind === "CANDLE_CLOSED")
      .map(e => [e.time_ms, e.candle!] as const));
    let lastTime = -1;
    let geometryIndex = 0;
    let activeMain: ReplayGeometry | undefined;
    const touches = new Set<string>();
    // Each observation must refer to the currently visible, frozen 1H line.
    // Streaming merge is O(candles + lines + observations), not quadratic.
    const projected = (line: ReplayGeometry, at_ms: number) =>
      line.from_price + (line.to_price - line.from_price) *
        (at_ms - line.from_ms) / (line.to_ms - line.from_ms);
    observations = object.observations.map(item => {
      const observation = record(item);
      const kind = observation.kind;
      const side = observation.side;
      const time_ms = positiveInteger(observation.time_ms, "observation.time_ms");
      const trend_version = positiveInteger(observation.trend_version, "trend_version");
      const price = safeNumber(observation.price, "observation.price");
      const line_price = safeNumber(observation.line_price, "line_price");
      if ((kind !== "MAIN_1H_TOUCH" && kind !== "MAIN_1H_REACTION") ||
          (side !== "BULL" && side !== "BEAR") ||
          observation.classification !== "UNVALIDATED_GEOMETRY_ONLY" ||
          !closedBars.has(time_ms) || time_ms < lastTime ||
          trend_version > time_ms - 300_000 || price <= 0 || line_price <= 0) {
        throw new Error("Недостоверное или будущее наблюдение линии");
      }
      while (geometry && geometryIndex < geometry.length &&
          geometry[geometryIndex].available_at_ms <= time_ms) {
        const line = geometry[geometryIndex++];
        if (line.kind === "MAIN_1H") activeMain = line;
      }
      const bar = closedBars.get(time_ms)!;
      if (!activeMain || activeMain.trend_version !== trend_version ||
          activeMain.side !== side || activeMain.trend_version > bar.start_ms ||
          bar.end_ms - bar.start_ms !== 300_000) {
        throw new Error("Наблюдение не связано с известной часовой линией 1–3");
      }
      const atOpen = projected(activeMain, bar.start_ms);
      const atClose = projected(activeMain, bar.end_ms);
      // Decimal-to-JS serialization tolerance, NOT a market/entry threshold.
      if (price !== bar.close ||
          Math.abs(line_price - atClose) > (1 + Math.abs(atClose)) * 1e-9) {
        throw new Error("Наблюдение не совпадает с закрытой свечой или трендовой");
      }
      lastTime = time_ms;
      const key = (stamp: number) => `${stamp}:${trend_version}:${side}`;
      if (kind === "MAIN_1H_TOUCH") {
        if (observation.touch_time_ms !== undefined) throw new Error("Касание содержит чужое время");
        if (bar.low > Math.min(atOpen, atClose) || bar.high < Math.max(atOpen, atClose) ||
            (side === "BULL" ? bar.close < atClose : bar.close > atClose)) {
          throw new Error("Касание не подтверждается OHLC и часовой трендовой");
        }
        touches.add(key(time_ms));
        return { kind, side, time_ms, price, line_price, trend_version,
          classification: "UNVALIDATED_GEOMETRY_ONLY" as const };
      }
      const touch_time_ms = positiveInteger(observation.touch_time_ms, "touch_time_ms");
      if (touch_time_ms !== bar.start_ms || !touches.has(key(touch_time_ms))) {
        throw new Error("Реакция без предыдущего подтверждённого касания");
      }
      const prior = closedBars.get(touch_time_ms);
      if (!prior || !(side === "BULL" ? bar.close > prior.close && bar.close > atClose :
          bar.close < prior.close && bar.close < atClose)) {
        throw new Error("Движение от трендовой не подтверждается закрытыми свечами");
      }
      return { kind, side, time_ms, touch_time_ms, price, line_price, trend_version,
        classification: "UNVALIDATED_GEOMETRY_ONLY" as const };
    });
  }
  // Wilder DMI is a read-only series aligned 1:1 with fully closed
  // market candles. An old JSON archive without DMI remains readable.
  let dmi_5m: ReplayDmi | undefined;
  if (object.dmi_5m !== undefined) {
    if (mode !== "MARKET_ONLY" && !(mode === "STRATEGY" && object.demo === true)) {
      throw new Error("ADX разрешён только для локальной истории и демо SIMULATION");
    }
    const rawDmi = record(object.dmi_5m);
    const closedEvents = events.filter((event) => event.kind === "CANDLE_CLOSED");
    if (rawDmi.source !== "SIMULATION" || rawDmi.timeframe !== "5m" ||
        !Array.isArray(rawDmi.points) || rawDmi.points.length !== closedEvents.length) {
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
      if (time_ms !== closedEvents[index].time_ms) {
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
    ...(observations ? { observations } : {}),
    ...(h017_blue_risk_previews ? { h017_blue_risk_previews } : {}),
    ...(geometry_warmup_hours !== undefined ? { geometry_warmup_hours } : {}),
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
  // Versioned synthetic fixture: enough closed bars for the 14/14 ADX warmup.
  // Its values are cross-checked against research.wilder_dmi in offline CI.
  const prices = [
    100, 101, 99, 102, 103, 104, 106, 107, 105, 104, 102, 101, 103, 105, 106, 105,
    103, 102, 100, 99, 101, 103, 105, 107, 109, 108, 107, 104, 101, 100, 99, 101,
    104, 107, 110, 112, 111, 109, 107, 105, 103, 106, 109, 112, 114, 113, 111, 108,
    106, 104, 103, 105, 108, 111, 115, 118, 116, 113, 110, 107, 108, 111, 114, 117,
  ];
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
  if (syntheticDmiFixture.values.length !== prices.length ||
      syntheticDmiFixture.di_length !== 14 || syntheticDmiFixture.adx_smoothing !== 14) {
    throw new Error("Несоответствие эталонного примера ADX");
  }
  const closedEvents = events.filter((e) => e.kind === "CANDLE_CLOSED");
  const dmi_5m = {
    source: "SIMULATION", timeframe: "5m",
    di_length: 14, adx_smoothing: 14,
    points: closedEvents.map((event, index) => ({
      time_ms: event.time_ms,
      plus_di: syntheticDmiFixture.values[index][0],
      minus_di: syntheticDmiFixture.values[index][1],
      adx: syntheticDmiFixture.values[index][2],
    })),
  };
  return parseReplayDocument({
    source: "SIMULATION", simulation_run_id: id, mode: "STRATEGY",
    events, demo: true, dmi_5m,
  });
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

/** Reveal only geometry observations whose M5 candle has actually closed. */
export function visibleObservations(
  document: ReplayDocument, closedTimeMs: number | null,
): ReplayObservation[] {
  if (document.mode !== "MARKET_ONLY" || !document.observations || closedTimeMs === null) {
    return [];
  }
  return document.observations.filter(item => item.time_ms <= closedTimeMs);
}

/** Only completed blue-open research previews, never trade signal/fill events. */
export function visibleH017BlueRiskPreviews(
  document: ReplayDocument, lastClosedMs: number | null,
): H017BlueRiskPreview[] {
  if (document.mode !== "MARKET_ONLY" || lastClosedMs === null) return [];
  return (document.h017_blue_risk_previews ?? []).filter(c => c.time_ms <= lastClosedMs);
}

/** For MARKET_ONLY, DMI has exactly one observation per completed 5m candle. */
export function visibleDmi(document: ReplayDocument, closedCandles: number): ReplayDmiPoint[] {
  if (!document.dmi_5m || (document.mode !== "MARKET_ONLY" && document.demo !== true)) return [];
  return document.dmi_5m.points.slice(
    0, Math.max(0, Math.min(Math.floor(closedCandles), document.dmi_5m.points.length)),
  );
}
