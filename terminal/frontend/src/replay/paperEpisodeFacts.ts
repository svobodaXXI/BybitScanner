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
  };
}

/** A timestamp is painted only on its original, independently CLOSED M5.
 * The exact exchange price is preserved; OHLC is never used as a substitute.
 */
function originalClosedCandle(candles: readonly ReplayCandle[], timeMs: number): ReplayCandle | null {
  let lo = 0, hi = candles.length - 1;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (candles[mid].end_ms < timeMs) lo = mid + 1;
    else hi = mid;
  }
  const bar = candles[lo];
  return bar && bar.start_ms <= timeMs && timeMs <= bar.end_ms ? bar : null;
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
