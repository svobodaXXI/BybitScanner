import { describe, expect, it } from "vitest";
import {
  nextClosedCandleCursor, parseReplayDocument, simulationActionJournal, visibleReplay,
} from "./replayModel";
import { visibleExecutionMarkers, visibleStopAmendMarkers } from "./executionMarkers";

const t = Date.UTC(2026, 10, 10, 8, 0);
const id = "l2_local_import";
const trade_id = `SIMULATION:${id}:IMPULSE_${t + 60_000}`;
const event = (kind: string, seq: number, at: number, rest: Record<string, unknown> = {}) =>
  ({ source: "SIMULATION", simulation_run_id: id, sequence: seq,
    kind, time_ms: at, ...rest });
const original = () => ({
  source: "SIMULATION", simulation_run_id: id,
  mode: "STRATEGY", demo: false, symbol: "ICNTUSDT", timeframe: "5m",
  market_data_source: "PINNED_BYBIT_PUBLIC_TRADES_PLUS_L2_EVENT_TIME_SIMULATION",
  execution_clock: "ORIGINAL_EVENT_TIME_NOT_OHLC_M1",
  execution_certainty: "CONDITIONAL_L2_NOT_REAL_EXCHANGE_FILLS",
  partial_and_be_markers: "EVENTS_ONLY_CONDITIONAL",
  events: [
    event("ENTRY_SIGNAL", 1, t + 60_000, {
      side: "LONG", price: 100, stop: 99, take: 104, trade_id,
    }),
    event("ENTRY_FILLED", 2, t + 60_010, {
      side: "LONG", price: 100, quantity: "100", fee_usdt: "0.6", trade_id,
    }),
    event("PARTIAL_FILLED", 3, t + 60_020, {
      side: "LONG", price: 102, quantity: "25", fee_usdt: "0.306",
      reason: "PARTIAL_TAKE", trade_id,
    }),
    event("STOP_AMENDED", 4, t + 60_030, {
      stop: 100.7, reason: "NET_BREAK_EVEN_AFTER_PARTIAL", trade_id,
    }),
    event("EXIT_FILLED", 5, t + 60_050, {
      side: "LONG", price: 100.7, quantity: "75", fee_usdt: "0.45315",
      net_usdt: "55.14085", pnl_percent: "0.5514085", reason: "STOP", trade_id,
    }),
    event("CANDLE_CLOSED", 6, t + 300_000, {
      candle: { start_ms: t, end_ms: t + 300_000,
        open: 100, high: 103, low: 99, close: 101, volume: 1000 },
      dmi: { time_ms: t + 300_000, plus_di: null, minus_di: null, adx: null },
    }),
  ],
});

describe("L2 original-event-time SIMULATION import", () => {
  it("plots exact fills and BE price only after a closed M5, never on the future", () => {
    const source = original();
    const replay = parseReplayDocument(source);
    expect(replay.market_data_source).toBe(source.market_data_source);
    expect(replay.execution_clock).toBe("ORIGINAL_EVENT_TIME_NOT_OHLC_M1");
    expect(visibleReplay(replay.events, 0).candles).toHaveLength(0);
    expect(visibleExecutionMarkers(replay.events.slice(0, 5), [])).toEqual([]);
    expect(visibleStopAmendMarkers(replay.events.slice(0, 5), [])).toEqual([]);
    expect(nextClosedCandleCursor(replay.events, 0)).toBe(6);
    const shown = visibleReplay(replay.events, 6);
    const markers = visibleExecutionMarkers(replay.events, shown.candles);
    expect(markers).toHaveLength(3);
    expect(markers.map(m => [m.time_ms, m.price, m.side])).toEqual([
      [t + 60_010, 100, "Buy"], [t + 60_020, 102, "Sell"],
      [t + 60_050, 100.7, "Sell"],
    ]);
    expect(markers[1].partial).toBe(true);
    expect(markers[0].partial).toBeUndefined();
    const stops = visibleStopAmendMarkers(replay.events, shown.candles);
    expect(stops).toEqual([
      { time_ms: t + 60_030, candle_start_ms: t, stop: 100.7, trade_id },
    ]);
    const actions = simulationActionJournal(replay).actions;
    expect(actions).toHaveLength(5);
    expect(actions.find(a => a.kind === "STOP_AMENDED")?.stop).toBe(100.7);
    expect(actions.find(a => a.kind === "PARTIAL_FILLED")?.quantity).toBe("25");
  });

  it("fails closed on forged source, no partial, duplicate, wrong residual or future-stop", () => {
    const source = original();
    const reject = (patch: (draft: ReturnType<typeof original>) => void) => {
      const copy = structuredClone(source);
      patch(copy);
      expect(() => parseReplayDocument(copy)).toThrow();
    };
    reject(x => { x.execution_clock = "OHLC_M1" as typeof x.execution_clock; });
    reject(x => { x.market_data_source = "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M" as typeof x.market_data_source; });
    reject(x => { x.execution_certainty = "REAL_EXCHANGE_FILL" as typeof x.execution_certainty; });
    reject(x => { x.events.splice(2, 1); });
    reject(x => { x.events[2].quantity = "150"; });
    reject(x => { x.events[4].quantity = "100"; });
    reject(x => { x.events[3].stop = -10; });
    reject(x => { x.events[1].fee_usdt = undefined; });
    reject(x => { x.events[4].trade_id = "SIMULATION:other:wrong"; });
    reject(x => { x.events[3].time_ms = t + 60_001; });
  });

  it("preserves legacy MARKET_ONLY and synthetic strategy imports", () => {
    const source = original();
    expect(() => parseReplayDocument({
      ...source, mode: "MARKET_ONLY",
      market_data_source: "BYBIT_PUBLIC_KLINE",
    })).toThrow();
  });
});
