/** Local read-only public M5 extension around a fixed original L2 receipt.
 * Archive provenance remains BYBIT_PUBLIC_KLINE. These bars NEVER become
 * execution history, L2 order book events or trading strategy decisions.
 */
import type { ReplayCandle, ReplayDocument } from "./replayModel";

export function selectedL2MarketContext(
  original: ReplayDocument,
  parts: readonly ReplayDocument[],
  startMs: number,
  endExclusiveMs: number,
): { before: ReplayCandle[]; after: ReplayCandle[]; covered: number } {
  if (original.execution_clock !== "ORIGINAL_EVENT_TIME_NOT_OHLC_M1" ||
      original.mode !== "STRATEGY" || !original.symbol ||
      !Number.isSafeInteger(startMs) || !Number.isSafeInteger(endExclusiveMs) ||
      endExclusiveMs <= startMs || endExclusiveMs - startMs > 90 * 86_400_000) {
    throw new Error("Недостоверный период просмотра L2");
  }
  const source = original.events.filter(e => e.kind === "CANDLE_CLOSED")
    .flatMap(e => e.candle ? [e.candle] : []);
  const first = source[0], last = source.at(-1);
  if (!first || !last || !parts.length)
    throw new Error("Исторический L2-контекст недоступен");
  const all: ReplayCandle[] = [];
  for (const part of parts) {
    if (part.mode !== "MARKET_ONLY" || part.market_data_source !== "BYBIT_PUBLIC_KLINE" ||
        part.symbol !== original.symbol || part.timeframe !== "5m") {
      throw new Error("Bybit M5: другой тикер или недостоверный источник");
    }
    for (const event of part.events) {
      if (event.kind !== "CANDLE_CLOSED" || !event.candle)
        throw new Error("Публичная история содержит торговые события");
      const bar = event.candle;
      if (bar.end_ms - bar.start_ms !== 300_000 ||
          (all.length && bar.start_ms !== all[all.length - 1].end_ms)) {
        throw new Error("В публичной истории M5 обнаружен пропуск/перекрытие");
      }
      all.push(bar);
    }
  }
  const selected = all.filter(c =>
    c.start_ms >= Math.floor(startMs / 300_000) * 300_000 &&
    c.end_ms <= endExclusiveMs);
  const before = selected.filter(c => c.end_ms <= first.start_ms);
  const after = selected.filter(c => c.start_ms >= last.end_ms);
  const overlap = selected.filter(c =>
    c.end_ms > first.start_ms && c.start_ms < last.end_ms);
  if (!overlap.length || !overlap.some(c => c.start_ms === first.start_ms))
    throw new Error("История Bybit не покрывает исходное окно L2");
  // Do not replace the original source M5; only check public context is
  // present and strictly ordered on either side.
  return { before, after, covered: selected.length };
}

/** Exact CLOSED-M5 inventory in the currently loaded local viewer.
 * In-memory bars only, never infer taker prints or L2 archive availability.
 * Even one missing selected M5 makes the requested range incomplete.
 */
export function loadedL2M5Coverage(
  original: ReplayDocument,
  before: readonly ReplayCandle[],
  after: readonly ReplayCandle[],
  startMs: number,
  endExclusiveMs: number,
): { complete: boolean; covered: number; required: number; firstMissingMs: number | null } {
  const interval = 300_000;
  if (original.execution_clock !== "ORIGINAL_EVENT_TIME_NOT_OHLC_M1" ||
      !Number.isSafeInteger(startMs) || !Number.isSafeInteger(endExclusiveMs) ||
      startMs < 0 || endExclusiveMs <= startMs ||
      endExclusiveMs - startMs > 90 * 86_400_000) {
    throw new Error("Нельзя подтвердить покрытие выбранного L2-периода");
  }
  const bars = [...before,
    ...original.events.filter(e => e.kind === "CANDLE_CLOSED")
      .flatMap(e => e.candle ? [e.candle] : []), ...after];
  const closed = new Set<number>();
  for (const c of bars) {
    if (c.end_ms - c.start_ms !== interval ||
        c.start_ms % interval !== 0) continue;
    closed.add(c.start_ms);
  }
  const first = Math.floor(startMs / interval) * interval;
  const end = Math.ceil(endExclusiveMs / interval) * interval;
  let required = 0, covered = 0, firstMissingMs: number | null = null;
  for (let at = first; at < end; at += interval) {
    required++;
    if (closed.has(at)) covered++;
    else if (firstMissingMs === null) firstMissingMs = at;
  }
  return { complete: firstMissingMs === null, required, covered, firstMissingMs };
}
