/** Owner-selected local research receipt import. No network, runtime, trading or
 * backtest. The source hashes here identify the one frozen historical study;
 * a self-reported hash is NOT a verified venue execution or a signature.
 */
import { parseReplayDocument, type ReplayDocument } from "./replayModel";

type Fields = Record<string, unknown>;
const BOOK_SHA = "79b032aafc5c97ea3790947cdd72347af83c88b9a1360aa219cdef5f5cbe54df";
const TRADE_SHA = "47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a";
const EXECUTION = "SIMULATION_HISTORICAL_TAKER_L2_EVENT_TIME_NOT_REAL_BYBIT_FILLS";
const decimal = /^(?:0|[1-9]\d*)(?:\.\d+)?$/;
const signed = /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/;

function object(value: unknown): Fields {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Повреждён локальный исследовательский отчёт");
  return value as Fields;
}
function number(value: unknown, name: string, allowNegative = false): number {
  if (typeof value !== "string" || !(allowNegative ? signed : decimal).test(value))
    throw new Error("Неверное числовое поле L2: " + name);
  const n = Number(value);
  if (!Number.isFinite(n) || (!allowNegative && n < 0))
    throw new Error("Недопустимое числовое поле L2: " + name);
  return n;
}
function same(a: unknown, b: unknown): boolean {
  return typeof a === "number" && Number.isFinite(a) &&
    typeof b === "number" && Number.isFinite(b) &&
    Math.abs(a - b) <= 1e-10 * Math.max(1, Math.abs(a), Math.abs(b));
}
function amount(fill: Fields, key: "quantity" | "fee_usdt", expected: string): string {
  if (fill[key] !== undefined && !same(number(fill[key], key), number(expected, key)))
    throw new Error("L2 квитанция не совпадает с исходным виртуальным эпизодом");
  return expected; // Restore omitted original receipt fields, never calculate from OHLC.
}

/** Also accepts a direct ReplayDocument, preserving the existing file import. */
export function parseLocalReplayUpload(input: unknown): ReplayDocument {
  const outer = object(input);
  if (outer.source === "SIMULATION") return parseReplayDocument(input);
  if (outer.state !== "VIRTUAL_L2_PROBE_CONDITIONAL" ||
      outer.scenario !== "ONE_BOUNDED_LOCAL_SIMULATION_NOT_REAL_BYBIT_EXECUTIONS" ||
      outer.l2_sha256 !== BOOK_SHA || outer.trade_gzip_sha256 !== TRADE_SHA ||
      typeof outer.code_sha !== "string" || !/^[0-9a-f]{40}$/.test(outer.code_sha)) {
    throw new Error("Это не исходный условный L2-отчёт ICNTUSDT");
  }
  const result = object(outer.result);
  if (result.symbol !== "ICNTUSDT" || result.execution_model !== EXECUTION ||
      result.l2_source_sha256 !== BOOK_SHA ||
      result.final_position_quantity !== "0" ||
      !Array.isArray(result.l2_episodes) || result.l2_episodes.length !== 4 ||
      result.virtual_fills !== 8) {
    throw new Error("Несовпадение исходного виртуального L2-журнала");
  }
  const replay = object(result.replay);
  if (replay.mode !== "STRATEGY" || replay.symbol !== "ICNTUSDT" ||
      !Array.isArray(replay.events) || replay.events.length > 100_000) {
    throw new Error("В отчёте нет исходного событийного графика L2");
  }

  const id = replay.simulation_run_id;
  if (typeof id !== "string" || !/^[a-zA-Z0-9_-]{1,100}$/.test(id))
    throw new Error("Неверный идентификатор локального replay");
  const ledger = new Map<string, Fields>();
  let net = 0;
  for (const row of result.l2_episodes) {
    const ep = object(row);
    const orderId = ep.order_id;
    if (typeof orderId !== "string" ||
        !/^IMPULSE_[0-9]+$/.test(orderId) || ledger.has(orderId) ||
        (ep.direction !== "LONG" && ep.direction !== "SHORT") ||
        (ep.exit_reason !== "STOP" && ep.exit_reason !== "TAKE") ||
        !Number.isSafeInteger(ep.entry_ms) || !Number.isSafeInteger(ep.exit_ms) ||
        (ep.entry_ms as number) >= (ep.exit_ms as number) ||
        ep.partial_quantity !== null) {
      throw new Error("Недостоверный оригинальный закрытый эпизод ICNT");
    }
    const qty = number(ep.quantity, "quantity");
    const entry = number(ep.entry_price, "entry_price");
    const exit = number(ep.exit_price, "exit_price");
    const entryFee = number(ep.entry_fee, "entry_fee");
    const exitFee = number(ep.exit_fee, "exit_fee");
    const episodeNet = number(ep.net_pnl_usdt, "net_pnl_usdt", true);
    if (qty <= 0 || entry <= 0 || exit <= 0 ||
        !same(episodeNet, (exit - entry) * qty *
          (ep.direction === "LONG" ? 1 : -1) - entryFee - exitFee)) {
      throw new Error("Расчёт эпизода не совпадает с исходным журналом");
    }
    net += episodeNet;
    ledger.set(orderId, ep);
  }
  if (!same(net, number(result.realized_net_pnl, "realized_net_pnl", true)))
    throw new Error("Сумма L2-эпизодов не равна исходному итоговому P&L");

  const seen = new Map<string, Set<string>>();
  const updated = replay.events.map(raw => {
    const event = object(raw);
    const kind = event.kind;
    if (kind !== "ENTRY_FILLED" && kind !== "EXIT_FILLED")
      return event;
    const tradeId = event.trade_id;
    if (typeof tradeId !== "string" || !tradeId.startsWith("SIMULATION:" + id + ":"))
      throw new Error("Исполнение не принадлежит локальному отчёту");
    const orderId = tradeId.slice(("SIMULATION:" + id + ":").length);
    const ep = ledger.get(orderId);
    if (!ep) throw new Error("Исполнение без оригинального L2-эпизода");
    const used = seen.get(orderId) ?? new Set<string>();
    if (used.has(kind)) throw new Error("Дублированное L2-исполнение");
    used.add(kind);
    seen.set(orderId, used);
    const entry = kind === "ENTRY_FILLED";
    const at = entry ? ep.entry_ms : ep.exit_ms;
    const price = entry ? ep.entry_price : ep.exit_price;
    if (event.time_ms !== at || !same(event.price, number(price, "price")) ||
        event.side !== ep.direction ||
        (!entry && (event.reason !== ep.exit_reason ||
          !same(number(event.net_usdt, "net_usdt", true),
                number(ep.net_pnl_usdt, "net_pnl_usdt", true))))) {
      throw new Error("Время, цена или P&L графика не совпали с виртуальной сделкой");
    }
    return {
      ...event,
      quantity: amount(event, "quantity", ep.quantity as string),
      fee_usdt: amount(event, "fee_usdt",
        (entry ? ep.entry_fee : ep.exit_fee) as string),
    };
  });
  if (seen.size !== 4 || [...seen.values()].some(k =>
      k.size !== 2 || !k.has("ENTRY_FILLED") || !k.has("EXIT_FILLED")))
    throw new Error("Исходные четыре L2-сделки представлены не полностью");
  return parseReplayDocument({ ...replay, events: updated });
}
