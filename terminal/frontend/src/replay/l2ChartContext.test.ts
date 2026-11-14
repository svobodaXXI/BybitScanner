import { describe, expect, it } from "vitest";
import { l2Prehistory, l2Posthistory, l2PresentationEvents } from "./l2ChartContext";
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
  it("reveals a trailing fourth L2 trade only on a later closed public M5", () => {
    const trade_id = "SIMULATION:test:IMPULSE_4";
    const trailing: ReplayEvent[] = [
      { source: "SIMULATION", simulation_run_id: "test", sequence: 2,
        kind: "ENTRY_FILLED", trade_id, side: "LONG", price: 1,
        quantity: "1000", fee_usdt: "0.6", time_ms: base + 300_001 },
      { source: "SIMULATION", simulation_run_id: "test", sequence: 3,
        kind: "EXIT_FILLED", trade_id, side: "LONG", price: 0.99,
        quantity: "1000", fee_usdt: "0.6",
        net_usdt: "-11.2", pnl_percent: "-1.12", reason: "STOP",
        time_ms: base + 300_050 },
    ];
    const source = { ...replay, events: [...replay.events, ...trailing] };
    const history = publicHistory([
      ...Array.from({ length: 288 }, (_, i) =>
        candle(base - 86_400_000 + i * 300_000)),
      ...Array.from({ length: 12 }, (_, i) =>
        candle(base + 300_000 + i * 300_000)),
    ]);
    const after = l2Posthistory(source, history);
    expect(after).toHaveLength(12);
    const merged = l2PresentationEvents(source, after);
    expect(merged).not.toBe(source.events);
    expect(source.events).toHaveLength(3);
    expect(merged.filter(x => x.kind === "ENTRY_FILLED")).toHaveLength(1);
    expect(merged.filter(x => x.kind === "EXIT_FILLED")).toHaveLength(1);
    const atFirstClose = merged.findIndex(x =>
      x.kind === "CANDLE_CLOSED" && x.time_ms === base + 600_000) + 1;
    expect(atFirstClose).toBe(4);
    expect(merged.slice(0, 1).some(x => x.kind === "ENTRY_FILLED")).toBe(false);
    expect(merged.slice(0, atFirstClose).filter(x => x.kind === "ENTRY_FILLED")).toHaveLength(1);
    expect(merged.slice(0, atFirstClose).filter(x => x.kind === "EXIT_FILLED")).toHaveLength(1);
    expect(merged[atFirstClose - 1].candle?.start_ms).toBe(base + 300_000);
  });
  it("rejects a gap in post-range M5", () => {
    expect(() => l2Posthistory(replay, publicHistory([
      candle(base + 300_000), candle(base + 900_000),
    ]))).toThrow();
  });
});
