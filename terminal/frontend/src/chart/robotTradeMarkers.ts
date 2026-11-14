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

/** Same candle-time association as Telegram's _candle_position; no nearest
 * fake fill marker or substituted OHLC price when evidence is outside chart.
 */
export function visibleRobotTradeMarkers(
  markers: readonly RobotTradeMarker[], candles: readonly Candle[], timeframe: string,
): VisibleRobotMarker[] {
  const minutes = Number(timeframe.endsWith("m") ? timeframe.slice(0, -1) :
    timeframe.endsWith("h") ? Number(timeframe.slice(0, -1)) * 60 : NaN);
  if (!Number.isSafeInteger(minutes) || minutes <= 0) return [];
  const duration = minutes * 60_000;
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
