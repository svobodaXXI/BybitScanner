/** Immutable PAPER execution evidence imported by the owner from Statistics.
 * NEVER turn these facts into SIMULATION events, fills, Robot decisions or PnL.
 * This is a strict local display-only adapter. Uploaded JSON is not signed.
 */
import type { ReplayCandle, ReplayDocument } from "./replayModel";
import { isReplayUsdtSymbol } from "./runSetup";

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

export type PaperCandidateGeometry = {
  pattern: string;
  timeframe: string;
  signal_time_ms: number;
  geometry: PaperOriginalGeometry;
};

export type GeometryRevisionObservation = {
  revision: number;
  event_time_ms: number;
  source_trade_id: string;
  reason: "CONTROL_CONTACT" | "OUTER_ENVELOPE";
  previous_extreme: string;
  trigger_price: string;
  previous_boundary: OriginalBoundary;
  current_boundary: OriginalBoundary;
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
  realized_price_pnl_usdt: string;
  known_execution_fees_usdt: string;
  pnl_usdt: string;
  execution_allocations: PaperAllocation[];
  setup_context?: PaperD2Context;
  candidate_geometry?: PaperCandidateGeometry;
  geometry_revisions?: GeometryRevisionObservation[];
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
  openedAt: number, linkageBasis = "D2_SETUP_ID_EQUALS_ARCHIVED_CANDIDATE_ID",
): PaperOriginalGeometry {
  const record = object(raw);
  if (record.schema !== "BYBITSCANNER_ARCHIVED_SIGNAL_GEOMETRY_V1"
      || record.source !== "ORIGINAL_TELEGRAM_SIGNAL_ARCHIVE"
      || record.linkage_basis !== linkageBasis
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

function parseCandidateGeometry(
  source: unknown, facts: Record<string, unknown>, opened: number,
  d2: PaperD2Context | undefined,
): PaperCandidateGeometry {
  const record = object(source);
  const proof = object(record.verified_signal);
  if (facts.owner !== "ROBOT" || facts.cohort !== "ROBOT" ||
      !d2 || !["D2_STORE_ABSENT", "NO_EXACT_EPISODE_LINK"].includes(d2.status) ||
      proof.status !== "PROVEN" || proof.trade_episode_id !== facts.trade_episode_id ||
      proof.source_revision !== facts.source_revision ||
      proof.provenance !== "DURABLE_ROBOT_TRADE_METADATA_NOT_ORIGINAL_GEOMETRY" ||
      !["EXACT_WEDGE_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE",
        "EXACT_ROBOT_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE"].includes(proof.evidence_scope as string))
    throw new Error("Архив не связан с точной сделкой Робота");
  const candidate = d2Text(proof.candidate_id, "candidate_id");
  const pattern = d2Text(proof.pattern, "pattern");
  const timeframe = d2Text(proof.source_timeframe, "source_timeframe");
  const signalTime = time(record.signal_time_ms, "signal_time_ms");
  const geometry = parseOriginalGeometry(record.geometry, {
    setup_id: candidate, symbol: facts.symbol as string, timeframe,
  }, opened, "EXACT_ROBOT_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE");
  if (signalTime > geometry.sent_at_ms)
    throw new Error("Время сигнала противоречит исходному архиву");
  return { pattern, timeframe, signal_time_ms: signalTime, geometry };
}

export function parseGeometryRevisions(
  raw: unknown, original: PaperOriginalGeometry | undefined, side: unknown, closed: number,
): GeometryRevisionObservation[] {
  const payload = object(raw);
  if (!original || payload.schema !== "BYBITSCANNER_WEDGE_GEOMETRY_REVISIONS_V1" ||
      payload.source !== "ROBOT_OBSERVED_PUBLIC_TRADES" ||
      payload.coverage !== "LOCAL_OBSERVATION_NOT_COMPLETE_EXCHANGE_TAPE" ||
      payload.candidate_id !== original.signal_id || payload.source_geometry_sha256 !== original.sha256 ||
      !Array.isArray(payload.events) || !payload.events.length || payload.events.length > 2000)
    throw new Error("Не подтверждена история перестроений");
  const strict = side === "LONG" ? "upper" : "lower";
  let previous = original.boundaries.find(b => b.boundary_id === strict && b.kind === "ray");
  let lastTime = original.sent_at_ms;
  const ids = new Set<string>();
  const equal = (a: OriginalBoundary, b: OriginalBoundary) =>
    a.anchors.every((v, i) => v.bar_open_time_ms === b.anchors[i]?.bar_open_time_ms &&
                              v.price === b.anchors[i]?.price);
  function boundary(raw: unknown, at: number): OriginalBoundary {
    const b = object(raw);
    if (b.boundary_id !== strict || b.kind !== "ray" ||
        !Array.isArray(b.anchors) || b.anchors.length !== 2)
      throw new Error("Некорректная строгая граница");
    const anchors = b.anchors.map((v: unknown) => {
      const a = object(v), stamp = time(a.bar_open_time_ms, "revision anchor");
      if (stamp >= at || typeof a.price !== "number" || !Number.isFinite(a.price) || a.price <= 0)
        throw new Error("Недопустимая точка перестроения");
      return { bar_open_time_ms: stamp, price: a.price };
    });
    if (anchors[0].bar_open_time_ms >= anchors[1].bar_open_time_ms ||
        (side === "LONG" ? anchors[0].price <= anchors[1].price : anchors[0].price >= anchors[1].price))
      throw new Error("Нарушено направление строгой границы");
    return { boundary_id: strict, kind: "ray", anchors };
  }
  return payload.events.map((rawEvent: unknown, i: number) => {
    const e = object(rawEvent);
    const at = time(e.event_time_ms, "revision timestamp");
    const tradeId = id(e.source_trade_id, "revision trade");
    const prior = decimal(e.previous_extreme, "previous extreme", true);
    const price = decimal(e.trigger_price, "trigger", true);
    const old = boundary(e.previous_boundary, at), current = boundary(e.current_boundary, at);
    if (!previous || e.revision !== i+1 || e.event !== "Паттерн перестроен" ||
        e.candidate_id !== original.signal_id || e.source_geometry_sha256 !== original.sha256 ||
        e.family !== (side === "LONG" ? "falling" : "rising") ||
        at < lastTime || at > closed || ids.has(tradeId) || !equal(old, previous) || equal(old,current) ||
        old.anchors[0].bar_open_time_ms !== current.anchors[0].bar_open_time_ms ||
        old.anchors[0].price !== current.anchors[0].price ||
        (e.reason !== "CONTROL_CONTACT" && e.reason !== "OUTER_ENVELOPE") ||
        (side === "LONG" ? Number(price) >= Number(prior) : Number(price) <= Number(prior)))
      throw new Error("Нарушена история перестроений");
    previous = current; lastTime = at; ids.add(tradeId);
    return { revision: i+1, event_time_ms: at, source_trade_id: tradeId,
      reason: e.reason, previous_extreme: prior, trigger_price: price,
      previous_boundary: old, current_boundary: current };
  });
}

export function visibleGeometryRevisions(facts: PaperEpisodeFacts | null, at: number | null) {
  return at === null ? [] : (facts?.geometry_revisions ?? []).filter(e => e.event_time_ms <= at);
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
  if (!isReplayUsdtSymbol(f.symbol))
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
  // Match the canonical Diary classification in ticker_finrez.py. The owner
  // selects a report scope; it does not imply who opened a joint episode.
  const owners = new Set(allocations.map(a => a.controller));
  const mixed = owners.has("ROBOT") && owners.has("MANUAL");
  const assisted = mixed && first.controller === "ROBOT" && last.controller === "MANUAL"
    && allocations.every(a => a.controller === "ROBOT" ||
      a.allocation_role === "REDUCE" || a.allocation_role === "CLOSE");
  const joint = mixed && !assisted && allocations.length >= 2
    && allocations.slice(1, -1).every(a =>
      a.allocation_role === "INCREASE" || a.allocation_role === "REDUCE");
  if ((f.cohort === "ROBOT" && (owners.size !== 1 || !owners.has("ROBOT")))
      || (f.cohort === "MANUAL" && (owners.size !== 1 || !owners.has("MANUAL")))
      || (f.cohort === "ROBOT_MANUAL_CLOSE" && !assisted)
      || (f.cohort === "JOINT_MANAGEMENT" && !joint))
    throw new Error("Источник управления противоречит исполнениям");

  const d2 = f.setup_context !== undefined
    ? parseD2Context(f.setup_context, f.symbol, f.side, first.controller, opened) : undefined;
  const candidate = f.candidate_geometry !== undefined
    ? parseCandidateGeometry(f.candidate_geometry, f, opened, d2) : undefined;
  let revisions: GeometryRevisionObservation[] | undefined;
  if (f.geometry_revisions !== undefined && f.owner === "ROBOT" && f.cohort === "ROBOT") {
    // Optional malformed geometry must not hide verified executions.
    try {
      revisions = parseGeometryRevisions(f.geometry_revisions, candidate?.geometry ??
        (d2?.status === "EXACT_D2_LINK" ? d2.original_geometry : undefined), f.side, closed);
    } catch { revisions = undefined; }
  }
  return {
    schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1", namespace: "PAPER_READ_ONLY",
    account_id: "paper", owner: f.owner, cohort: f.cohort as PaperEpisodeFacts["cohort"],
    source_revision: f.source_revision as number, trade_episode_id: f.trade_episode_id,
    symbol: f.symbol, side: f.side, opened_at_ms: opened, closed_at_ms: closed,
    realized_price_pnl_usdt: realized, known_execution_fees_usdt: fees,
    pnl_usdt: pnl, execution_allocations: allocations,
    ...(d2 ? { setup_context: d2 } : {}),
    ...(candidate ? { candidate_geometry: candidate } : {}),
    ...(revisions ? { geometry_revisions: revisions } : {}),
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

/** Count only revealed, source-proven PAPER allocations; never virtual fills. */
export function visiblePaperExecutionCounts(
  facts: PaperEpisodeFacts | null, overlay: PaperOverlay, candles: readonly ReplayCandle[],
): { entries: number; exits: number } {
  const visible = new Set(revealedPaperMarkers(overlay, candles).map(marker => marker.execution_id));
  let entries = 0, exits = 0;
  for (const item of facts?.execution_allocations ?? []) {
    if (!visible.has(item.execution_id)) continue;
    if (item.allocation_role === "OPEN" || item.allocation_role === "REVERSAL_OPEN" ||
        item.allocation_role === "INCREASE") entries++;
    else if (item.allocation_role === "REDUCE" || item.allocation_role === "CLOSE") exits++;
  }
  return { entries, exits };
}
