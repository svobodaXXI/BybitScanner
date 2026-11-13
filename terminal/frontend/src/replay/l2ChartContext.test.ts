import { describe, expect, it } from "vitest";
import { l2Prehistory } from "./l2ChartContext";
import type { ReplayCandle, ReplayDocument, ReplayEvent } from "./replayModel";

const base = Date.UTC(2026, 10, 10, 8);
const candle = (start_ms: number): ReplayCandle => ({
  start_ms, end_ms: start_ms + 300_000,
  open: 1, high: 1.1, low: 0.9, close: 1, volume: 1,
});
const event = (c: ReplayCandle): ReplayEvent => ({
  source: "SIMULATION", simulation_run_id: "test", sequence: 1,
  kind: "CANDLE_CLOSED", time_ms: c.end_ms, candle: c,
});
const replay = {
  mode: "STRATEGY", symbol: "ICNTUSDT",
  execution_clock: "ORIGINAL_EVENT_TIME_NOT_OHLC_M1",
  events: [event(candle(base))],
} as ReplayDocument;
const publicHistory = (bars: ReplayCandle[]) => ({
  mode: "MARKET_ONLY", symbol: "ICNTUSDT",
  market_data_source: "BYBIT_PUBLIC_KLINE",
  events: bars.map(event),
}) as ReplayDocument;

describe("L2 chart-only M5 prehistory", () => {
  it("selects only closed preceding M5 and cannot add future candles", () => {
    const bars = Array.from({ length: 288 }, (_, i) =>
      candle(base - 86_400_000 + i * 300_000));
    const selected = l2Prehistory(replay, publicHistory([
      ...bars, candle(base), candle(base + 300_000),
    ]));
    expect(selected).toHaveLength(288);
    expect(selected.at(-1)?.end_ms).toBe(base);
    expect(replay.events).toHaveLength(1);
    expect(replay.events[0].candle?.start_ms).toBe(base);
  });
  it("rejects mismatched symbols and incomplete prehistory", () => {
    expect(() => l2Prehistory(replay, {
      ...publicHistory([candle(base - 300_000)]), symbol: "BTCUSDT",
    })).toThrow();
    expect(() => l2Prehistory(replay, publicHistory([
      candle(base - 900_000), candle(base - 300_000),
    ]))).toThrow();
  });
  it("never invents history when the public source is absent", () => {
    expect(() => l2Prehistory(replay, publicHistory([candle(base)]))).toThrow();
  });
});
