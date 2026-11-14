/** Read-only M5 prehistory for an L2 report. Never extends its event stream,
 * virtual exchange, execution clock, fills or financial results.
 */
import type { ReplayCandle, ReplayDocument } from "./replayModel";

export function l2Prehistory(
  replay: ReplayDocument, publicHistory: ReplayDocument,
): ReplayCandle[] {
  if (replay.execution_clock !== "ORIGINAL_EVENT_TIME_NOT_OHLC_M1" ||
      replay.mode !== "STRATEGY" ||
      publicHistory.mode !== "MARKET_ONLY" ||
      publicHistory.market_data_source !== "BYBIT_PUBLIC_KLINE" ||
      !replay.symbol || publicHistory.symbol !== replay.symbol) {
    throw new Error("Контекст M5 не соответствует исходному L2-прогону");
  }
  const first = replay.events.find(e => e.kind === "CANDLE_CLOSED" && e.candle)?.candle;
  if (!first) throw new Error("В L2-прогоне отсутствует исходная M5");
  const bars = publicHistory.events.filter(e => e.kind === "CANDLE_CLOSED")
    .map(e => e.candle)
    .filter((c): c is ReplayCandle => c !== undefined &&
      c.end_ms <= first.start_ms && c.end_ms > first.start_ms - 86_400_000);
  if (bars.length === 0 || bars.length > 288 ||
      bars.some((bar, index) => bar.end_ms - bar.start_ms !== 300_000 ||
        (index > 0 && bars[index - 1].end_ms !== bar.start_ms))) {
    throw new Error("Публичная предыстория M5 неполная или несогласованная");
  }
  return bars;
}

/** Strict public M5 after the last original closed M5, at most one hour.
 * These candles are observation-only. Neither this nor the next helper
 * changes the source's original events, fills or financial ledger.
 */
export function l2Posthistory(
  replay: ReplayDocument, publicHistory: ReplayDocument,
): ReplayCandle[] {
  if (replay.execution_clock !== "ORIGINAL_EVENT_TIME_NOT_OHLC_M1" ||
      replay.mode !== "STRATEGY" ||
      publicHistory.mode !== "MARKET_ONLY" ||
      publicHistory.market_data_source !== "BYBIT_PUBLIC_KLINE" ||
      !replay.symbol || publicHistory.symbol !== replay.symbol) {
    throw new Error("Публичное продолжение не соответствует L2-источнику");
  }
  const original = replay.events.filter(e => e.kind === "CANDLE_CLOSED")
    .map(e => e.candle);
  const last = original.at(-1);
  if (!last) throw new Error("В L2-отчёте нет закрытых M5");
  const bars = publicHistory.events.filter(e => e.kind === "CANDLE_CLOSED")
    .map(e => e.candle)
    .filter((c): c is ReplayCandle => c !== undefined &&
      c.start_ms >= last.end_ms && c.start_ms < last.end_ms + 3_600_000);
  if (bars.length === 0 || bars.length > 12 ||
      bars.some((bar, index) => bar.end_ms - bar.start_ms !== 300_000 ||
        bar.start_ms !== last.end_ms + index * 300_000)) {
    throw new Error("Неполное или несогласованное публичное продолжение M5");
  }
  return bars;
}

/** Separate VISUAL clock: insert closed PUBLIC M5 after the original replay.
 * The returned list is never persisted, imported as a trading run, or passed
 * to the Robot; existing L2 events remain unmodified and in original time.
 * A virtual L2 fill is exposed only on reaching its public closed M5.
 */
export function l2PresentationEvents(
  replay: ReplayDocument, after: readonly ReplayCandle[],
): ReplayDocument["events"] {
  if (!after.length) return replay.events;
  if (replay.execution_clock !== "ORIGINAL_EVENT_TIME_NOT_OHLC_M1")
    throw new Error("Пострыночные свечи разрешены только в просмотре L2");
  const added = after.map(bar => ({
    source: "SIMULATION" as const,
    simulation_run_id: replay.simulation_run_id,
    kind: "CANDLE_CLOSED" as const,
    time_ms: bar.end_ms,
    candle: bar,
  }));
  return [...replay.events, ...added].sort((a, b) =>
    a.time_ms - b.time_ms || (a.kind === "CANDLE_CLOSED" ? -1 : 0)
      - (b.kind === "CANDLE_CLOSED" ? -1 : 0))
    .map((event, index) => ({ ...event, sequence: index + 1 }));
}
