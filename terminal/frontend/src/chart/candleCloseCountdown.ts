import { CHART_TIMEFRAMES, type ChartTimeframe } from "../marketData/timeframes";

const DURATION_MS: Record<ChartTimeframe, number> = {
  "15s": 15_000,
  "1m": 60_000,
  "5m": 300_000,
  "15m": 900_000,
  "1h": 3_600_000,
  "1d": 86_400_000,
};

/**
 * Remaining time until the currently streamed candle closes (UTC/exchange clock).
 * A historical or stale last bar has no live countdown: never imply it is current.
 * This function is presentation-only; it never mutates candles or timestamps.
 */
export function currentCandleCloseCountdown(
  latestBarStart: string | null,
  timeframe: string,
  nowMs: number,
): string | null {
  if (!latestBarStart || !CHART_TIMEFRAMES.some((tf) => tf === timeframe)) return null;
  if (!Number.isFinite(nowMs)) return null;
  const openMs = Date.parse(latestBarStart);
  if (!Number.isFinite(openMs)) return null;
  const duration = DURATION_MS[timeframe as ChartTimeframe];
  // Require an actual live bar of the chosen interval; never show a countdown
  // for frozen Editor signals or for an old/future candle after feed interruption.
  const closingMs = openMs + duration;
  if (nowMs < openMs || nowMs >= closingMs) return null;

  const seconds = Math.ceil((closingMs - nowMs) / 1000);
  const pad = (value: number) => String(value).padStart(2, "0");
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return duration > 3_600_000
    ? `${pad(hours)}:${pad(minutes)}:${pad(remainder)}`
    : `${pad(minutes)}:${pad(remainder)}`;
}
