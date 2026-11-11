/** Immutable PAPER execution evidence imported by the owner from Statistics.
 * NEVER turn these facts into SIMULATION events, fills, Robot decisions or PnL.
 * This is a strict local display-only adapter. Uploaded JSON is not signed.
 */
import type { ReplayCandle, ReplayDocument } from "./replayModel";

export type PaperAllocation = {
  execution_id: string;
  order_id: string;
  order_side: "Buy" | "Sell";
  execution_price: string;
  allocated_quantity: string;
  allocated_fee: string;
  occurred_at_ms: number;
  allocation_role: "OPEN" | "REVERSAL_OPEN" | "INCREASE" | "REDUCE" | "CLOSE";
  controller: "ROBOT" | "MANUAL";
};

export type D2DecisionObservation = {
  decision_event_id: string;
  kind: "STRATEGY" | "RISK" | "SETUP_OUTCOME";
  previous_state: string | null;
  next_state: string;
  reason_code: string;
  controller: "ROBOT" | "MANUAL" | "EXTERNAL" | "NONE";
  origin: "ROBOT" | "TERMINAL_MANUAL" | "EXTERNAL";
  occurred_at_ms: number;
};
export type OriginalBoundary = {
  boundary_id: string;
  kind: "ray" | "segment" | "horizontal" | "horizontal-ray";
  anchors: { bar_open_time_ms: number; price: number }[];
};
export type PaperOriginalGeometry = {
  signal_id: string;
  sent_at_ms: number;
  sha256: string;
  boundaries: OriginalBoundary[];
};

export type PaperD2Context =
  | {
    status: "EXACT_D2_LINK";
    geometry_status: "NOT_EXPORTED" | "ORIGINAL_ARCHIVE_HASH_VERIFIED";
    original_geometry?: PaperOriginalGeometry;
    decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG";
    setup: {
      setup_instance_id: string; setup_id: string; symbol: string;
      direction: "LONG" | "SHORT"; timeframe: string; pattern: string;
      strategy_version: string; entry_mode: string;
      origin: "ROBOT" | "TERMINAL_MANUAL"; created_at_ms: number;
      has_feature_snapshot_ref: boolean;
    };
    decisions: D2DecisionObservation[];
  }
  | {
    status: "D2_STORE_ABSENT" | "EVIDENCE_UNAVAILABLE" |
      "NO_EXACT_EPISODE_LINK" | "CONFLICTING_D2_LINK" |
      "INCOMPLETE_D2_DECISIONS";
    geometry_status: "NOT_EXPORTED";
    decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG";
  };

export type PaperEpisodeFacts = {
  schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1";
  namespace: "PAPER_READ_ONLY";
  account_id: "paper";
  owner: "ROBOT" | "MANUAL";
  cohort: "ROBOT" | "MANUAL" | "ROBOT_MANUAL_CLOSE" | "JOINT_MANAGEMENT";
  source_revision: number;
  trade_episode_id: string;
  symbol: string;
  side: "LONG" | "SHORT";
  opened_at_ms: number;
  closed_at_ms: number;
  pnl_usdt: string;
  execution_allocations: PaperAllocation[];
  setup_context?: PaperD2Context;
};

export type PaperMarker = {
  time_ms: number;
  candle_start_ms: number;
  price: number;
  order_side: "Buy" | "Sell";
  execution_id: string;
};
export type PaperOverlay =
  | { status: "WAIT_MARKET"; reason: string; markers: [] }
  | { status: "MATCHED"; reason: ""; markers: PaperMarker[] };

function object(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new Error("Неверный JSON фактов PAPER");
  return value as Record<string, unknown>;
}
function decimal(value: unknown, label: string, positive = false): string {
  if (typeof value !== "string" || value.length > 100 ||
      !/^[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?$/.test(value)
      || !Number.isFinite(Number(value)) || (positive && Number(value) <= 0))
    throw new Error("Некорректное числовое поле: " + label);
  return value; // Never round actual exchange prices, quantities or fees.
}
function time(value: unknown, label: string): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0)
    throw new Error("Некорректное время: " + label);
  return value as number;
}
function id(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length > 300 || !value.trim())
    throw new Error("Неизвестный идентификатор: " + label);
  return value;
}

const D2_REASON = "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG";
const D2_UNPROVEN = new Set([
  "D2_STORE_ABSENT", "EVIDENCE_UNAVAILABLE", "NO_EXACT_EPISODE_LINK",
  "CONFLICTING_D2_LINK", "INCOMPLETE_D2_DECISIONS",
]);

function d2Text(value: unknown, label: string): string {
  const raw = id(value, label);
  if (raw.length > 256) throw new Error("Слишком длинное поле D2: " + label);
  return raw;
}

function parseOriginalGeometry(
  raw: unknown, setup: { setup_id: string; symbol: string; timeframe: string },
  openedAt: number,
): PaperOriginalGeometry {
  const record = object(raw);
  if (record.schema !== "BYBITSCANNER_ARCHIVED_SIGNAL_GEOMETRY_V1"
      || record.source !== "ORIGINAL_TELEGRAM_SIGNAL_ARCHIVE"
      || record.linkage_basis !== "D2_SETUP_ID_EQUALS_ARCHIVED_CANDIDATE_ID"
      || record.integrity !== "LOCAL_ARCHIVE_HASH_ONLY_NOT_CRYPTOGRAPHIC_PROOF"
      || record.signal_id !== setup.setup_id
      || typeof record.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(record.sha256))
    throw new Error("Архивная геометрия не соответствует доказанному сигналу");
  const sentAt = time(record.sent_at_ms, "source sent");
  if (sentAt > openedAt) throw new Error("Исходный сигнал появился после исполнения");
  const snapshot = object(record.snapshot);
  if (snapshot.schema_version !== 1 || snapshot.signal_id !== setup.setup_id
      || snapshot.symbol !== setup.symbol || String(snapshot.timeframe) !== setup.timeframe
      || !Array.isArray(snapshot.bars) || snapshot.bars.length < 2
      || snapshot.bars.length > 2000 || !Array.isArray(snapshot.boundaries)
      || !snapshot.boundaries.length || snapshot.boundaries.length > 16)
    throw new Error("Невалидная идентичность исходного окна геометрии");
  const barTimes = new Set<number>();
  let previous = -1;
  for (const rawBar of snapshot.bars) {
    const bar = object(rawBar);
    const stamp = time(bar.open_time_ms, "source candle");
    const vals = [bar.open, bar.high, bar.low, bar.close];
    if (stamp <= previous || stamp > sentAt ||
        vals.some(v => typeof v !== "number" || !Number.isFinite(v) || v <= 0) ||
        (bar.high as number) < (bar.low as number) ||
        (bar.open as number) < (bar.low as number) ||
        (bar.open as number) > (bar.high as number) ||
        (bar.close as number) < (bar.low as number) ||
        (bar.close as number) > (bar.high as number))
      throw new Error("Повреждённые свечи архивного оригинала");
    previous = stamp;
    barTimes.add(stamp);
  }
  const allowed: Record<string, number> = {
    ray: 2, segment: 2, horizontal: 1, "horizontal-ray": 1,
  };
  const ids = new Set<string>();
  const boundaries: OriginalBoundary[] = [];
  for (const rawLine of snapshot.boundaries) {
    const line = object(rawLine);
    const boundaryId = id(line.boundary_id, "boundary_id");
    const need = allowed[line.kind as string];
    if (boundaryId.length > 128 || ids.has(boundaryId) || !need ||
        !Array.isArray(line.anchors) || line.anchors.length !== need)
      throw new Error("Неизвестная граница архивного оригинала");
    ids.add(boundaryId);
    let prev = -1;
    const anchors = line.anchors.map((rawAnchor: unknown) => {
      const a = object(rawAnchor);
      const at = time(a.bar_open_time_ms, "boundary anchor");
      if (!barTimes.has(at) || at <= prev || typeof a.price !== "number" ||
          !Number.isFinite(a.price) || a.price <= 0)
        throw new Error("Граница не подтверждена исходной свечой");
      prev = at;
      return { bar_open_time_ms: at, price: a.price };
    });
    boundaries.push({
      boundary_id: boundaryId,
      kind: line.kind as OriginalBoundary["kind"],
      anchors,
    });
  }
  return {
    signal_id: setup.setup_id, sent_at_ms: sentAt,
    sha256: record.sha256, boundaries,
  };
}

function parseD2Context(
  source: unknown, symbol: string, side: "LONG" | "SHORT",
  openingController: "ROBOT" | "MANUAL", openedAt: number,
): PaperD2Context {
  const row = object(source);
  if (row.source !== "TRADING_DIARY_D2"
      || !["NOT_EXPORTED", "ORIGINAL_ARCHIVE_HASH_VERIFIED"].includes(row.geometry_status as string)
      || row.decision_scope !== D2_REASON)
    throw new Error("Неизвестное происхождение D2-связи");
  if (D2_UNPROVEN.has(row.status as string)) {
    if (row.setup !== undefined || row.decisions !== undefined ||
        row.original_geometry !== undefined || row.geometry_status !== "NOT_EXPORTED")
      throw new Error("Недоказанная D2-связь содержит вымышленные события");
    return {
      status: row.status as Exclude<PaperD2Context["status"], "EXACT_D2_LINK">,
      geometry_status: "NOT_EXPORTED", decision_scope: D2_REASON,
    };
  }
  if (row.status !== "EXACT_D2_LINK" ||
      row.consistency !== "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER")
    throw new Error("Неизвестная согласованность D2-снимка");
  const setup = object(row.setup);
  const expectedOrigin: "ROBOT" | "TERMINAL_MANUAL" =
    openingController === "ROBOT" ? "ROBOT" : "TERMINAL_MANUAL";
  if (setup.symbol !== symbol || setup.direction !== side ||
      setup.origin !== expectedOrigin || typeof setup.has_feature_snapshot_ref !== "boolean"
      || !Array.isArray(row.decisions) || row.decisions.length < 2 ||
      row.decisions.length > 1000)
    throw new Error("D2 setup не соответствует фактической сделке");
  time(setup.created_at_ms, "setup.created_at_ms");
  time(row.linked_at_ms, "linked_at_ms");
  const details = {
    setup_instance_id: d2Text(setup.setup_instance_id, "setup_instance_id"),
    setup_id: d2Text(setup.setup_id, "setup_id"),
    symbol, direction: side,
    timeframe: d2Text(setup.timeframe, "timeframe"),
    pattern: d2Text(setup.pattern, "pattern"),
    strategy_version: d2Text(setup.strategy_version, "strategy_version"),
    entry_mode: d2Text(setup.entry_mode, "entry_mode"),
    origin: expectedOrigin,
    created_at_ms: setup.created_at_ms as number,
    has_feature_snapshot_ref: setup.has_feature_snapshot_ref as boolean,
  };
  d2Text(row.order_plan_id, "order_plan_id");
  const events: D2DecisionObservation[] = [];
  let lastTime = -1;
  let lastId = "";
  const unique = new Set<string>();
  for (const raw of row.decisions) {
    const e = object(raw);
    const decisionId = d2Text(e.decision_event_id, "decision_event_id");
    const stamp = time(e.occurred_at_ms, "decision.occurred_at_ms");
    if (!["STRATEGY", "RISK", "SETUP_OUTCOME"].includes(e.kind as string) ||
        !["ROBOT", "MANUAL", "NONE", "EXTERNAL"].includes(e.controller as string) ||
        !["ROBOT", "TERMINAL_MANUAL", "EXTERNAL"].includes(e.origin as string) ||
        (e.previous_state !== null && typeof e.previous_state !== "string") ||
        stamp < details.created_at_ms || stamp < lastTime ||
        (stamp === lastTime && decisionId <= lastId) || unique.has(decisionId))
      throw new Error("Недостоверная хронология решений D2");
    unique.add(decisionId); lastTime = stamp; lastId = decisionId;
    events.push({
      decision_event_id: decisionId,
      kind: e.kind as D2DecisionObservation["kind"],
      previous_state: e.previous_state === null ? null : d2Text(e.previous_state, "previous_state"),
      next_state: d2Text(e.next_state, "next_state"),
      reason_code: d2Text(e.reason_code, "reason_code"),
      controller: e.controller as D2DecisionObservation["controller"],
      origin: e.origin as D2DecisionObservation["origin"],
      occurred_at_ms: stamp,
    });
  }
  if (!events.some(e => e.kind === "STRATEGY") ||
      !events.some(e => e.kind === "RISK"))
    throw new Error("Отсутствуют доказанные решения стратегии и риска");
  if (row.geometry_status === "NOT_EXPORTED" && row.original_geometry !== undefined)
    throw new Error("Недоказанная архивная геометрия");
  const original = row.geometry_status === "ORIGINAL_ARCHIVE_HASH_VERIFIED"
    ? parseOriginalGeometry(row.original_geometry, details, openedAt) : undefined;
  return {
    status: "EXACT_D2_LINK",
    geometry_status: original ? "ORIGINAL_ARCHIVE_HASH_VERIFIED" : "NOT_EXPORTED",
    ...(original ? { original_geometry: original } : {}),
    decision_scope: D2_REASON, setup: details, decisions: events,
  };
}

/** Own immutable facts only; no remote requests, persistence or exchange access. */
export function parsePaperEpisodeFacts(input: unknown): PaperEpisodeFacts {
  const f = object(input);
  if (f.ok !== true || f.schema !== "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1"
      || f.namespace !== "PAPER_READ_ONLY" || f.source !== "PAPER_EXECUTIONS_ATTRIBUTED"
      || f.account_id !== "paper" || f.pnl_basis !== "REALIZED_PRICE_MINUS_EXECUTION_FEES"
      || f.replay_evidence !== "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES")
    throw new Error("Файл не является экспортом фактов закрытой PAPER-сделки");
  if (f.owner !== "ROBOT" && f.owner !== "MANUAL")
    throw new Error("Неизвестный источник управления сделкой");
  const cohorts = f.owner === "ROBOT"
    ? ["ROBOT", "ROBOT_MANUAL_CLOSE", "JOINT_MANAGEMENT"]
    : ["MANUAL", "JOINT_MANAGEMENT"];
  if (!cohorts.includes(f.cohort as string))
    throw new Error("Категория управления не соответствует владельцу");
  if (typeof f.trade_episode_id !== "string" || !/^te_[a-f0-9]{24}$/.test(f.trade_episode_id))
    throw new Error("Недостоверный ID эпизода");
  if (typeof f.symbol !== "string" || !/^[A-Z0-9]{3,30}USDT$/.test(f.symbol))
    throw new Error("Неверный тикер эпизода");
  if (f.side !== "LONG" && f.side !== "SHORT")
    throw new Error("Неизвестное направление эпизода");
  const opened = time(f.opened_at_ms, "opened_at_ms");
  const closed = time(f.closed_at_ms, "closed_at_ms");
  if (closed < opened || !Number.isSafeInteger(f.source_revision) || (f.source_revision as number) <= 0)
    throw new Error("Несогласованная версия или время эпизода");
  const realized = decimal(f.realized_price_pnl_usdt, "realized_price_pnl_usdt");
  const fees = decimal(f.known_execution_fees_usdt, "known_execution_fees_usdt");
  const pnl = decimal(f.pnl_usdt, "pnl_usdt");
  if (Math.abs((Number(realized) - Number(fees)) - Number(pnl)) >
      Math.max(1e-9, Math.abs(Number(pnl)) * 1e-10))
    throw new Error("PNL в выгрузке противоречит известным комиссиям");
  if (!Array.isArray(f.execution_allocations) || !f.execution_allocations.length ||
      f.execution_allocations.length > 10000)
    throw new Error("Нет ограниченного набора исходных исполнений");
  const openingSide = f.side === "LONG" ? "Buy" : "Sell";
  let previous = opened;
  const allocations = f.execution_allocations.map((raw, i) => {
    const item = object(raw);
    const role = item.allocation_role;
    if (!["OPEN", "REVERSAL_OPEN", "INCREASE", "REDUCE", "CLOSE"].includes(role as string)
        || !["Buy", "Sell"].includes(item.order_side as string)
        || !["ROBOT", "MANUAL"].includes(item.controller as string))
      throw new Error("Неизвестная роль исполнения или контроллер");
    const stamp = time(item.occurred_at_ms, "occurred_at_ms");
    if (stamp < opened || stamp > closed || stamp < previous)
      throw new Error("Хронология фактических исполнений нарушена");
    previous = stamp;
    const entering = role === "OPEN" || role === "REVERSAL_OPEN" || role === "INCREASE";
    if (item.order_side !== (entering ? openingSide : openingSide === "Buy" ? "Sell" : "Buy"))
      throw new Error("Сторона исполнения противоречит направлению сделки");
    return {
      execution_id: id(item.execution_id, "execution_id"),
      order_id: id(item.order_id, "order_id"),
      order_side: item.order_side as "Buy" | "Sell",
      execution_price: decimal(item.execution_price, "execution_price", true),
      allocated_quantity: decimal(item.allocated_quantity, "allocated_quantity", true),
      allocated_fee: decimal(item.allocated_fee, "allocated_fee"),
      occurred_at_ms: stamp,
      allocation_role: role as PaperAllocation["allocation_role"],
      controller: item.controller as "ROBOT" | "MANUAL",
    };
  });
  const first = allocations[0], last = allocations[allocations.length - 1];
  if (!["OPEN", "REVERSAL_OPEN"].includes(first.allocation_role) ||
      last.allocation_role !== "CLOSE" || first.occurred_at_ms !== opened ||
      last.occurred_at_ms !== closed)
    throw new Error("Эпизод не подтверждён как завершённый");
  if ((f.cohort === "ROBOT" && allocations.some(a => a.controller !== "ROBOT"))
      || (f.cohort === "MANUAL" && allocations.some(a => a.controller !== "MANUAL"))
      || (f.cohort === "ROBOT_MANUAL_CLOSE" &&
          (first.controller !== "ROBOT" || last.controller !== "MANUAL"))
      || (f.cohort === "JOINT_MANAGEMENT" &&
          (first.controller !== "ROBOT" || last.controller !== "ROBOT" ||
           !allocations.some(a => a.controller === "MANUAL" && a.allocation_role === "INCREASE"))))
    throw new Error("Источник управления противоречит исполнениям");

  return {
    schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1", namespace: "PAPER_READ_ONLY",
    account_id: "paper", owner: f.owner, cohort: f.cohort as PaperEpisodeFacts["cohort"],
    source_revision: f.source_revision as number, trade_episode_id: f.trade_episode_id,
    symbol: f.symbol, side: f.side, opened_at_ms: opened, closed_at_ms: closed,
    pnl_usdt: pnl, execution_allocations: allocations,
    ...(f.setup_context !== undefined ? {
      setup_context: parseD2Context(f.setup_context, f.symbol, f.side, first.controller, opened),
    } : {}),
  };
}

/** A timestamp is painted only on its original, independently CLOSED M5.
 * At an exact M5 boundary it belongs to the NEW bar, never the preceding one.
 * The exact exchange price is preserved; OHLC is never used as a substitute.
 */
function originalClosedCandle(candles: readonly ReplayCandle[], timeMs: number): ReplayCandle | null {
  let lo = 0, hi = candles.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (candles[mid].end_ms <= timeMs) lo = mid + 1;
    else hi = mid;
  }
  const bar = candles[lo];
  return bar && bar.start_ms <= timeMs && timeMs < bar.end_ms ? bar : null;
}

export function matchPaperFactsToMarket(
  facts: PaperEpisodeFacts | null, document: ReplayDocument,
): PaperOverlay {
  if (!facts) return { status: "WAIT_MARKET", reason: "Нет выбранной PAPER-сделки", markers: [] };
  if (document.demo || document.mode !== "MARKET_ONLY" ||
      !document.market_data_source || document.symbol !== facts.symbol)
    return {
      status: "WAIT_MARKET",
      reason: "Нужен отдельный публичный M5-архив " + facts.symbol + " за время сделки",
      markers: [],
    };
  const candles = document.events.filter(e => e.kind === "CANDLE_CLOSED" && !!e.candle)
    .map(e => e.candle as ReplayCandle);
  if (!candles.length) return { status: "WAIT_MARKET", reason: "Нет закрытых M5", markers: [] };
  const markers: PaperMarker[] = [];
  for (const item of facts.execution_allocations) {
    const bar = originalClosedCandle(candles, item.occurred_at_ms);
    if (!bar) return {
      status: "WAIT_MARKET",
      reason: "В архиве отсутствуют закрытые M5 для всех исполнений выбранной сделки",
      markers: [],
    };
    markers.push({
      time_ms: item.occurred_at_ms, candle_start_ms: bar.start_ms,
      price: Number(item.execution_price), order_side: item.order_side,
      execution_id: item.execution_id,
    });
  }
  return { status: "MATCHED", reason: "", markers };
}

export function revealedPaperMarkers(
  overlay: PaperOverlay, candles: readonly ReplayCandle[],
): PaperMarker[] {
  if (overlay.status !== "MATCHED") return [];
  const seen = new Set(candles.map(c => c.start_ms));
  return overlay.markers.filter(item => seen.has(item.candle_start_ms));
}

/** Preselect only full UTC days for the existing loopback PUBLIC M5 loader.
 * This provides market context, never historical Robot decisions or
 * authoritative execution candles. A >7-day episode must be handled
 * explicitly instead of silently truncating the requested interval.
 */
export function publicHistoryDaysForPaperEpisode(
  facts: PaperEpisodeFacts,
): { start: string; end: string } | null {
  const dayMs = 86_400_000;
  const startMs = Math.floor(facts.opened_at_ms / dayMs) * dayMs;
  const endExclusiveMs = Math.floor(facts.closed_at_ms / dayMs) * dayMs + dayMs;
  if (!Number.isSafeInteger(startMs) || !Number.isSafeInteger(endExclusiveMs) ||
      endExclusiveMs <= startMs || endExclusiveMs - startMs > 7 * dayMs)
    return null;
  return {
    start: new Date(startMs).toISOString().slice(0, 10),
    end: new Date(endExclusiveMs).toISOString().slice(0, 10),
  };
}
