/** Replay-only adapter to the EXISTING Robot/Telegram execution-marker contract.
 *
 * Source of truth:
 * - robot_position_view.TradeMarker(time_ms, price, side, filled)
 * - robot_position_chart._candle_position / _draw_marker:
 *   Buy = green ^ (#00a152), Sell = red v (#d50000), drawn on ACTUAL fill price.
 * We do not import the Robot runtime, change its renderer or mix PAPER records
 * with local SIMULATION events.
 */
import type { ReplayCandle, ReplayEvent } from "./replayModel";

export const TELEGRAM_BUY_COLOR = "#00a152";
export const TELEGRAM_SELL_COLOR = "#d50000";

export type ReplayExecutionMarker = {
  time_ms: number;
  candle_start_ms: number;
  price: number;
  side: "Buy" | "Sell";
  trade_id: string;
  partial?: true;
};

export type ReplayStopAmendMarker = {
  time_ms: number;
  candle_start_ms: number;
  stop: number;
  trade_id: string;
};

function originalCandleAt(
  time: number, candles: readonly ReplayCandle[], includeEnd: boolean,
): ReplayCandle | undefined {
  return candles.find(c =>
    (includeEnd && time === c.end_ms) ||
    (c.start_ms <= time && time < c.end_ms));
}

export function visibleStopAmendMarkers(
  events: readonly ReplayEvent[],
  candles: readonly ReplayCandle[],
): ReplayStopAmendMarker[] {
  return events.flatMap(event => {
    if (event.kind !== "STOP_AMENDED" || !event.trade_id ||
        event.stop === undefined || !Number.isFinite(event.stop) ||
        event.stop <= 0) return [];
    const candle = originalCandleAt(event.time_ms, candles, false);
    return candle ? [{ time_ms: event.time_ms, candle_start_ms: candle.start_ms,
      stop: event.stop, trade_id: event.trade_id }] : [];
  });
}

/** Map a confirmed fill to the actual OHLC interval, not to a nearby arrow slot. */
export function visibleExecutionMarkers(
  events: readonly ReplayEvent[],
  candles: readonly ReplayCandle[],
): ReplayExecutionMarker[] {
  const result: ReplayExecutionMarker[] = [];
  for (const event of events) {
    if (event.kind !== "ENTRY_FILLED" && event.kind !== "PARTIAL_FILLED" &&
        event.kind !== "EXIT_FILLED") continue;
    if (!event.trade_id || !event.side || event.price === undefined ||
        !Number.isFinite(event.price) || event.price <= 0) continue;
    // An exit at the exact close belongs to the just-closed M5. A new
    // opening entry never backdates into the previous candle.
    const bar = originalCandleAt(event.time_ms, candles,
      event.kind === "EXIT_FILLED" || event.kind === "PARTIAL_FILLED");
    if (!bar) continue; // Fail closed: never invent a future or off-window candle.
    const isBuy = event.kind === "ENTRY_FILLED"
      ? event.side === "LONG"
      : event.side === "SHORT";
    result.push({
      time_ms: event.time_ms,
      candle_start_ms: bar.start_ms,
      price: event.price, // Do NOT substitute OHLC, last price or candle high/low.
      side: isBuy ? "Buy" : "Sell",
      trade_id: event.trade_id,
      ...(event.kind === "PARTIAL_FILLED" ? { partial: true as const } : {}),
    });
  }
  return result;
}
