/** Display-only candle close countdown; never changes exchange timestamps. */
const INTERVAL_MS: Record<string, number> = {
  "15s": 15_000, "1m": 60_000, "5m": 300_000, "15m": 900_000,
  "1h": 3_600_000, "1d": 86_400_000,
  "1": 60_000, "5": 300_000, "15": 900_000,
  "60": 3_600_000, "D": 86_400_000,
};

export type CandleCloseStatus =
  | { status: "LIVE"; label: string }
  | { status: "STALE"; label: string }
  | { status: "UNAVAILABLE"; label: "" };

export function candleCloseStatus(
  lastCandleOpen: string | undefined,
  timeframe: string,
  nowMs: number,
): CandleCloseStatus {
  const interval = INTERVAL_MS[timeframe];
  if (!interval || !lastCandleOpen || !Number.isFinite(nowMs))
    return { status: "UNAVAILABLE", label: "" };
  const last = Date.parse(lastCandleOpen);
  if (!Number.isFinite(last) || last > nowMs || nowMs - last > interval * 2)
    return { status: "STALE", label: "Нет свежих свечей" };
  const remaining = interval - (nowMs % interval);
  const seconds = Math.ceil(remaining / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  const label = hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  return { status: "LIVE", label };
}
