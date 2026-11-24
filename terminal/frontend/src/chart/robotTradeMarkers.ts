import type { Candle } from "../contracts/marketData";
import { TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR } from "../replay/executionMarkers";

export type RobotTradeMarker = {
  time_ms: number;
  price: string;
  side: "Buy" | "Sell";
  filled: boolean;
};

export type VisibleRobotMarker = {
  logical: number;
  price: number;
  side: "Buy" | "Sell";
  filled: boolean;
};

export { TELEGRAM_BUY_COLOR, TELEGRAM_SELL_COLOR };

/** Shared exact-price triangle geometry for Telegram/Terminal trade fills. */
export function tradeTrianglePoints(x: number, y: number, side: "Buy" | "Sell"): string {
  return side === "Buy"
    ? `${x},${y - 8} ${x - 7},${y + 6} ${x + 7},${y + 6}`
    : `${x},${y + 8} ${x - 7},${y - 6} ${x + 7},${y - 6}`;
}

/** Same candle-time association as Telegram's _candle_position; no nearest
 * fake fill marker or substituted OHLC price when evidence is outside chart.
 */
export function visibleRobotTradeMarkers(
  markers: readonly RobotTradeMarker[], candles: readonly Candle[], timeframe: string,
): VisibleRobotMarker[] {
  const match = /^(\d+)(s|m|h|d)$/.exec(timeframe);
  if (!match) return [];
  const unit = { s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000 }[match[2] as "s" | "m" | "h" | "d"];
  const duration = Number(match[1]) * unit;
  if (!Number.isSafeInteger(duration) || duration <= 0) return [];
  const bars = candles.map((c) => Date.parse(c.time));
  if (!bars.every((time) => Number.isSafeInteger(time)) ||
      bars.some((time, i) => i > 0 && time <= bars[i - 1])) return [];
  const result: VisibleRobotMarker[] = [];
  for (const marker of markers) {
    const price = Number(marker.price);
    if (!(Number.isFinite(price) && price > 0) ||
        !Number.isSafeInteger(marker.time_ms) ||
        !["Buy", "Sell"].includes(marker.side) || typeof marker.filled !== "boolean")
      continue;
    const i = bars.findIndex((open, index) => {
      const close = index + 1 < bars.length ? Math.min(bars[index + 1], open + duration) : open + duration;
      return open <= marker.time_ms && marker.time_ms < close;
    });
    if (i < 0) continue;
    result.push({ logical: i, price, side: marker.side, filled: marker.filled });
  }
  return result;
}
