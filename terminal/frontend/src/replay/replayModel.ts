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
/** Confirmed second MAIN_1H touch: purple structural invalidation level, NOT a signal. */
export type ReplayPriorLevel = {
  side: "BULL" | "BEAR";
  at_ms: number;
  price: number;
  available_at_ms: number;
  trend_version: number;
  /** End of this version's reign, known only after another qualifying trend appears. */
  superseded_at_ms?: number;
};
/** A closed H1 candle beyond the prior, followed by the next H1 OPEN beyond it. */
export type ReplayPriorBreak = {
  kind: "PRIOR_CLOSE_NEXT_OPEN";
  confirmed_at_ms: number;
  previous_side: "BULL" | "BEAR";
  new_side: "BULL" | "BEAR";
  prior_price: number;
  trend_version: number;
  prior_at_ms: number;
  hourly_close_ms: number;
  next_hour_open_ms: number;
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
export type ReplayDmiCrossing = {
  time_ms: number;
  side: "PLUS" | "MINUS";
  direction: "UP" | "DOWN";
  comparator: "OPPOSITE_DI" | "ADX" | "LEVEL_20";
};
export type ReplayDmiPoint = {
  time_ms: number; // Close time, never the opening time of an unfinished candle.
  plus_di: number | null;
  minus_di: number | null;
  adx: number | null;
  crossings?: ReplayDmiCrossing[]; // Legacy snapshots without crossings are allowed.
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
/** Counterfactual first-touch observations; NEVER simulated fills or trade results. */
export type H017FirstTouch = "TARGET_FIRST" | "STOP_FIRST" | "BOTH_SAME_M5" | "UNRESOLVED";
export type H017CandidateStudyRow = {
  candidate_time_ms: number;
  open_ms: number;
  side: "LONG" | "SHORT";
  /** Crossings known on the last CLOSED M5 immediately before the opening. */
  crossings_at_open: ReplayDmiCrossing[] | null;
  first_touch: H017FirstTouch;
  resolved_at_ms?: number;
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
    // Check claimed crossings against the numeric closed-candle series.
    // They corroborate geometry; they are never entries, fills, or vetoes.
    const verifiedPoints: ReplayDmiPoint[] = points.map((point, index) => {
      const raw = record((rawDmi.points as unknown[])[index]);
      if (raw.crossings === undefined) return point; // Older archive format.
      if (!Array.isArray(raw.crossings) || raw.crossings.length > 6) {
        throw new Error("Недостоверные пересечения ADX/DMI");
      }
      const expected: ReplayDmiCrossing[] = [];
      const prev = points[index - 1];
      if (prev) {
        for (const side of ["PLUS", "MINUS"] as const) {
          const before = side === "PLUS" ? prev.plus_di : prev.minus_di;
          const after = side === "PLUS" ? point.plus_di : point.minus_di;
          if (before === null || after === null) continue;
          const comparators: Array<[ReplayDmiCrossing["comparator"], number | null, number | null]> = [
            ["OPPOSITE_DI", side === "PLUS" ? prev.minus_di : prev.plus_di,
              side === "PLUS" ? point.minus_di : point.plus_di],
            ["LEVEL_20", 20, 20],
            ["ADX", prev.adx, point.adx],
          ];
          for (const [comparator, beforeRef, afterRef] of comparators) {
            if (beforeRef === null || afterRef === null) continue;
            const direction = before <= beforeRef && after > afterRef ? "UP" :
              before >= beforeRef && after < afterRef ? "DOWN" : null;
            if (direction) expected.push({ time_ms: point.time_ms, side, direction, comparator });
          }
        }
      }
      const crossings: ReplayDmiCrossing[] = raw.crossings.map(value => {
        const item = record(value);
        if ((item.side !== "PLUS" && item.side !== "MINUS") ||
            (item.direction !== "UP" && item.direction !== "DOWN") ||
            (item.comparator !== "OPPOSITE_DI" && item.comparator !== "ADX" &&
              item.comparator !== "LEVEL_20")) {
          throw new Error("Недостоверные пересечения ADX/DMI");
        }
        return {
          time_ms: positiveInteger(item.time_ms, "crossing.time_ms"),
          side: item.side, direction: item.direction, comparator: item.comparator,
        };
      });
      if (crossings.length !== expected.length ||
          crossings.some((cross, i) => cross.time_ms !== expected[i].time_ms ||
            cross.side !== expected[i].side ||
            cross.direction !== expected[i].direction ||
            cross.comparator !== expected[i].comparator)) {
        throw new Error("Пересечение ADX/DMI не совпадает с закрытыми значениями");
      }
      return { ...point, crossings };
    });
    dmi_5m = { source: "SIMULATION", timeframe: "5m", di_length, adx_smoothing, points: verifiedPoints };
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

/** Full immutable SIMULATION action report; playback cursor never deletes history.
 * Export only actions present in the source events. No fabricated orders, fees,
 * quantities, fills, positions, or PnL are inferred from price candles.
 */
export function simulationActionJournal(document: ReplayDocument) {
  const actions = document.events.filter(event => event.kind !== "CANDLE_CLOSED").map(event => ({
    event_id: `${event.simulation_run_id}:${event.sequence}`,
    simulation_run_id: event.simulation_run_id,
    sequence: event.sequence,
    time_ms: event.time_ms,
    kind: event.kind,
    ...(document.symbol ? { symbol: document.symbol } : {}),
    ...(event.trade_id ? { trade_id: event.trade_id } : {}),
    ...(event.side ? { side: event.side } : {}),
    ...(event.price !== undefined ? { price: event.price } : {}),
    ...(event.stop !== undefined ? { stop: event.stop } : {}),
    ...(event.take !== undefined ? { take: event.take } : {}),
    ...(event.reason ? { reason: event.reason } : {}),
    comment: event.kind === "ENTRY_SIGNAL" ? `Сигнал ${event.side ?? ""}` :
      event.kind === "ENTRY_FILLED" ? `Вход ${event.side ?? ""}` :
      `Выход ${event.reason ?? ""}`,
  }));
  return {
    source: "SIMULATION" as const,
    simulation_run_id: document.simulation_run_id,
    report_kind: "RECORDED_ACTIONS_ONLY" as const,
    actions,
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

/**
 * Historic purple priors are derived from the already-confirmed 1--3 H1 line's
 * SECOND wick extremum (point 3), not from an extra fitted candle or a
 * speculative 5m contact. The market feed updates this MAIN line only when
 * another four-pivot structure is confirmed, including a new extreme in the
 * direction of the trend. A touch alone cannot move the prior.
 *
 * Each prefix has its own immutable visible versions, with no look-ahead.
 * Structural reversal is NOT inferred from a wick piercing this price.
 */
export function visiblePriorLevels(
  document: ReplayDocument, closedTimeMs: number | null,
): ReplayPriorLevel[] {
  if (document.mode !== "MARKET_ONLY" || closedTimeMs === null) return [];
  const result: ReplayPriorLevel[] = [];
  for (const line of document.geometry ?? []) {
    if (line.available_at_ms > closedTimeMs) break;
    if (line.kind !== "MAIN_1H") continue;
    const last = result.at(-1);
    if (last && last.at_ms === line.to_ms &&
        last.price === line.to_price && last.side === line.side) continue;
    if (last) last.superseded_at_ms = line.available_at_ms;
    result.push({
      side: line.side, at_ms: line.to_ms, price: line.to_price,
      available_at_ms: line.available_at_ms, trend_version: line.trend_version,
    });
  }
  return result;
}

/**
 * Evidence of the owner's close-beyond-prior / next-hour-open-beyond-prior
 * sequence. No wick-only violation, guessed threshold or unfinished H1 close.
 * The first fully closed M5 of the next H1 is the earliest replay observation
 * that exposes the new hour's actual OPEN. This is structural research only,
 * NEVER an entry/fill or licence to fabricate an opposite yellow line.
 */
export function visiblePriorBreaks(
  document: ReplayDocument, closedTimeMs: number | null,
): ReplayPriorBreak[] {
  if (document.mode !== "MARKET_ONLY" || closedTimeMs === null) return [];
  const candles = document.events.filter(e => e.kind === "CANDLE_CLOSED").map(e => e.candle!);
  const result: ReplayPriorBreak[] = [];
  const emitted = new Set<string>();
  const hourMs = 3_600_000, fiveMs = 300_000;
  for (let i = 12; i < candles.length; i++) {
    const next = candles[i];
    if (next.end_ms > closedTimeMs) break;
    if (next.start_ms % hourMs !== 0 || next.end_ms !== next.start_ms + fiveMs) continue;
    const first = candles[i - 12];
    if (first.start_ms !== next.start_ms - hourMs) continue;
    let completeHour = true;
    for (let j = 0; j < 12; j++) {
      const bar = candles[i - 12 + j];
      if (bar.start_ms !== first.start_ms + j * fiveMs ||
          bar.end_ms !== bar.start_ms + fiveMs) {
        completeHour = false;
        break;
      }
    }
    if (!completeHour) continue;
    const previousHourClose = candles[i - 1];
    const prior = visiblePriorLevels(document, previousHourClose.end_ms).at(-1);
    // The prior must already have existed BEFORE the candle being tested
    // closed, or the event would be a hindsight-confirmed violation.
    if (!prior || prior.available_at_ms >= previousHourClose.end_ms) continue;
    const broken = prior.side === "BULL"
      ? previousHourClose.close < prior.price && next.open < prior.price
      : previousHourClose.close > prior.price && next.open > prior.price;
    if (!broken) continue;
    const key = [prior.side, prior.at_ms, prior.trend_version].join(":");
    if (emitted.has(key)) continue;
    emitted.add(key);
    result.push({
      kind: "PRIOR_CLOSE_NEXT_OPEN", confirmed_at_ms: next.end_ms,
      previous_side: prior.side, new_side: prior.side === "BULL" ? "BEAR" : "BULL",
      prior_price: prior.price, prior_at_ms: prior.at_ms,
      trend_version: prior.trend_version,
      hourly_close_ms: previousHourClose.end_ms, next_hour_open_ms: next.start_ms,
    });
  }
  return result;
}

/** Immutable versions retained for review after revisions and structural breaks. */
export type ReplayGeometryVersion = ReplayGeometry & { superseded_at_ms?: number };

export function visibleGeometryHistory(
  document: ReplayDocument, closedTimeMs: number | null,
): ReplayGeometryVersion[] {
  if (document.mode !== "MARKET_ONLY" || closedTimeMs === null) return [];
  const versions: ReplayGeometryVersion[] = [];
  const latest = new Map<ReplayGeometry["kind"], number>();
  for (const line of document.geometry ?? []) {
    if (line.available_at_ms > closedTimeMs) break;
    const prev = latest.get(line.kind);
    if (prev !== undefined) versions[prev].superseded_at_ms = line.available_at_ms;
    latest.set(line.kind, versions.length);
    versions.push({ ...line });
  }
  const breaks = new Map(
    visiblePriorBreaks(document, closedTimeMs).map(event =>
      [event.trend_version, event.confirmed_at_ms] as const),
  );
  for (const version of versions) {
    const brokenAt = breaks.get(version.trend_version);
    if (brokenAt !== undefined) {
      version.superseded_at_ms = Math.min(version.superseded_at_ms ?? Infinity, brokenAt);
    }
  }
  return versions;
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
  // A broken trend is historical, never active while the research stream
  // waits for confirmed opposite 1--3/2--4 anchors.
  if (main && visiblePriorBreaks(document, closedTimeMs)
    .some(event => event.trend_version === main.trend_version)) return [];
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

/**
 * Study the first observed touch of FROZEN research target/stop prices.
 * This is not a trading exit rule: overlapping independent candidates count
 * independently, the within-candle order is UNKNOWN when both levels touch,
 * and fees/slippage/fills/PnL are deliberately excluded.
 *
 * Use the exact preceding closed M5 for DMI corroboration at candidate OPEN.
 * No near-neighbour window or directional veto is invented.
 */
export function studyH017BlueCandidates(document: ReplayDocument): H017CandidateStudyRow[] {
  if (document.mode !== "MARKET_ONLY" || !document.h017_blue_risk_previews) return [];
  const bars = document.events.filter(e => e.kind === "CANDLE_CLOSED").map(e => e.candle!);
  if (!bars.length) return [];
  const openIndex = new Map(bars.map((bar, index) => [bar.start_ms, index]));
  const dmiAtClose = new Map((document.dmi_5m?.points ?? []).map(p => [p.time_ms, p]));
  // Segment tree makes first-touch searches O(log N) per candidate, not O(N²).
  let capacity = 1;
  while (capacity < bars.length) capacity *= 2;
  const highs = new Float64Array(capacity * 2).fill(-Infinity);
  const lows = new Float64Array(capacity * 2).fill(Infinity);
  bars.forEach((bar, i) => { highs[capacity + i] = bar.high; lows[capacity + i] = bar.low; });
  for (let i = capacity - 1; i > 0; i--) {
    highs[i] = Math.max(highs[2 * i], highs[2 * i + 1]);
    lows[i] = Math.min(lows[2 * i], lows[2 * i + 1]);
  }
  const firstTouch = (
    node: number, left: number, right: number, since: number,
    side: "LONG" | "SHORT", stop: number, target: number,
  ): number => {
    if (right <= since || left >= bars.length) return -1;
    const mayHit = side === "LONG"
      ? highs[node] >= target || lows[node] <= stop
      : lows[node] <= target || highs[node] >= stop;
    if (!mayHit) return -1;
    if (right - left === 1) return left;
    const mid = (left + right) / 2;
    const earlier = firstTouch(node * 2, left, mid, since, side, stop, target);
    return earlier >= 0 ? earlier : firstTouch(node * 2 + 1, mid, right, since, side, stop, target);
  };
  return document.h017_blue_risk_previews
    .filter(p => p.risk_status === "RISK_PASS")
    .map(p => {
      const barIndex = openIndex.get(p.open_ms);
      if (barIndex === undefined || p.stop_price === undefined) {
        throw new Error("H-017 study requires a validated, frozen candidate");
      }
      const lastKnown = dmiAtClose.get(p.open_ms);
      const crossingEvidence = lastKnown?.adx != null && lastKnown.crossings !== undefined
        ? lastKnown.crossings : null;
      const found = firstTouch(1, 0, capacity, barIndex, p.side, p.stop_price, p.target_price);
      if (found < 0) return {
        candidate_time_ms: p.time_ms, open_ms: p.open_ms, side: p.side,
        crossings_at_open: crossingEvidence, first_touch: "UNRESOLVED" as const,
      };
      const bar = bars[found];
      const hitTarget = p.side === "LONG" ? bar.high >= p.target_price : bar.low <= p.target_price;
      const hitStop = p.side === "LONG" ? bar.low <= p.stop_price : bar.high >= p.stop_price;
      return {
        candidate_time_ms: p.time_ms, open_ms: p.open_ms, side: p.side,
        crossings_at_open: crossingEvidence,
        first_touch: hitTarget && hitStop ? "BOTH_SAME_M5" as const
          : hitTarget ? "TARGET_FIRST" as const : "STOP_FIRST" as const,
        resolved_at_ms: bar.end_ms,
      };
    });
}

/** Future OHLC outcomes are never revealed before their own candle closes. */
export function visibleH017CandidateStudy(
  study: readonly H017CandidateStudyRow[], lastClosedMs: number | null,
): H017CandidateStudyRow[] {
  if (lastClosedMs === null) return [];
  return study.filter(row => row.candidate_time_ms <= lastClosedMs).map(row =>
    row.resolved_at_ms !== undefined && row.resolved_at_ms > lastClosedMs
      ? { ...row, first_touch: "UNRESOLVED", resolved_at_ms: undefined }
      : row,
  );
}

/** For MARKET_ONLY, DMI has exactly one observation per completed 5m candle. */
export function visibleDmi(document: ReplayDocument, closedCandles: number): ReplayDmiPoint[] {
  if (!document.dmi_5m || (document.mode !== "MARKET_ONLY" && document.demo !== true)) return [];
  return document.dmi_5m.points.slice(
    0, Math.max(0, Math.min(Math.floor(closedCandles), document.dmi_5m.points.length)),
  );
}
