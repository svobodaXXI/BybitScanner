export const CHART_TIMEFRAMES = ["15s", "1m", "5m", "15m", "1h", "1d"] as const;

export type ChartTimeframe = (typeof CHART_TIMEFRAMES)[number];

export const BYBIT_INTERVAL_BY_TIMEFRAME: Record<ChartTimeframe, string> = {
  "15s": "15s",
  "1m": "1",
  "5m": "5",
  "15m": "15",
  "1h": "60",
  "1d": "D",
};
