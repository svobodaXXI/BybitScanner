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
