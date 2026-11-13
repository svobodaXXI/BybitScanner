import { describe, expect, it } from "vitest";
import { selectedL2MarketContext } from "./l2PeriodContext";
import type { ReplayDocument, ReplayCandle, ReplayEvent } from "./replayModel";

const base = Date.UTC(2026, 10, 10, 8);
const interval = 300_000;
const bar = (start_ms: number): ReplayCandle => ({
  start_ms, end_ms: start_ms + interval,
  open: 1, close: 1, high: 1.1, low: .9, volume: 5,
});
const original = {
  mode: "STRATEGY", symbol: "ICNTUSDT",
  execution_clock: "ORIGINAL_EVENT_TIME_NOT_OHLC_M1",
  simulation_run_id: "owner", source: "SIMULATION",
  events: [0,1,2].map((i): ReplayEvent => ({
    source: "SIMULATION", simulation_run_id: "owner",
    kind: "CANDLE_CLOSED", sequence: i+1,
    time_ms: base + (i+1)*interval, candle: bar(base+i*interval),
  })),
} as ReplayDocument;
const history = (start: number, count: number, symbol="ICNTUSDT") => ({
  mode: "MARKET_ONLY", symbol, timeframe: "5m",
  market_data_source: "BYBIT_PUBLIC_KLINE",
  events: Array.from({ length: count }, (_, i) => ({
    kind: "CANDLE_CLOSED", candle: bar(start + i * interval),
  })),
}) as ReplayDocument;

describe("selected Bybit extension around imported original L2", () => {
  it("adds history on either side without replacing any original fills", () => {
    const start = base - 12*interval;
    const end = base + 20*interval;
    const a = history(start, 18);
    const b = history(start + 18*interval, 14);
    const result = selectedL2MarketContext(original, [a,b], start,end);
    expect(result.covered).toBe(32);
    expect(result.before).toHaveLength(12);
    expect(result.after).toHaveLength(17);
    expect(result.after[0].start_ms).toBe(base + 3*interval);
    expect(original.events).toHaveLength(3);
  });
  it("fails closed for missing archived history, mismatched symbol, and gaps", () => {
    const start = base - 12*interval, end=base+20*interval;
    expect(() => selectedL2MarketContext(original,[history(start, 32, "BTCUSDT")],start,end)).toThrow();
    expect(() => selectedL2MarketContext(original,[
      history(start, 18),history(start+19*interval, 13),
    ],start,end)).toThrow(/пропуск/);
    expect(() => selectedL2MarketContext(original,[
      history(base+interval,4),
    ],start,end)).toThrow(/исходное окно/);
  });
});
