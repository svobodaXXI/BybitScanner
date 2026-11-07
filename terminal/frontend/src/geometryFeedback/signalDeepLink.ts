import { CHART_TIMEFRAMES, type ChartTimeframe } from "../marketData/timeframes";

export type SignalWorkspaceLink = {
  mode: "EDITOR" | "TERMINAL";
  symbol: string;
  timeframe: ChartTimeframe;
  signalId: string | null;
};

/** Read-only interpretation of the requested view; never authorizes any trade. */
export function parseSignalWorkspaceLink(search: string): SignalWorkspaceLink | null {
  const params = new URLSearchParams(search);
  const mode = params.get("mode");
  if (mode !== "EDITOR" && mode !== "TERMINAL") return null;
  const symbol = params.get("symbol");
  const timeframe = params.get("timeframe");
  if (!symbol || !/^[A-Z0-9]{2,32}USDT$/.test(symbol)) return null;
  if (!timeframe || !CHART_TIMEFRAMES.includes(timeframe as ChartTimeframe)) return null;
  const signalId = params.get("signal_id");
  if (signalId !== null && (!/^[A-Za-z0-9_.:-]{1,128}$/.test(signalId))) return null;
  return { mode, symbol, timeframe: timeframe as ChartTimeframe, signalId };
}
