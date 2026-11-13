import { describe, expect, it } from "vitest";
import { parseLocalReplayUpload } from "./l2ReplayUpload";
import { simulationActionJournal, visibleReplay } from "./replayModel";
import { visibleExecutionMarkers } from "./executionMarkers";

const t = Date.UTC(2026, 10, 10, 8, 0);
const id = "icnt_l2_local_receipt";
const BOOK_SHA = "79b032aafc5c97ea3790947cdd72347af83c88b9a1360aa219cdef5f5cbe54df";
const TRADE_SHA = "47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a";
const output = () => {
  const nets = ["-1.2", "8.8", "-11.2", "8.8"];
  const sides = ["LONG", "LONG", "SHORT", "LONG"];
  const exits = ["100", "101", "101", "101"];
  const orders = Array.from({ length: 4 }, (_, i) => ({
    order_id: "IMPULSE_" + (t + i * 10_000), direction: sides[i],
    entry_ms: t + i * 10_000 + 1_000,
    exit_ms: t + i * 10_000 + 2_000,
    entry_price: "100", exit_price: exits[i],
    entry_fee: "0.6", exit_fee: "0.6", quantity: "10",
    partial_quantity: null, exit_reason: i === 1 || i === 3 ? "TAKE" : "STOP",
    net_pnl_usdt: nets[i],
  }));
  const events: Record<string, unknown>[] = [];
  for (const row of orders) {
    const identity = "SIMULATION:" + id + ":" + row.order_id;
    const start = {
      source: "SIMULATION", simulation_run_id: id, trade_id: identity,
      side: row.direction,
    };
    events.push({
      ...start, kind: "ENTRY_FILLED", sequence: events.length + 1,
      time_ms: row.entry_ms, price: 100,
      // Original owner receipt predates later addition of quantity/fee markers.
    });
    events.push({
      ...start, kind: "EXIT_FILLED", sequence: events.length + 1,
      time_ms: row.exit_ms, price: Number(row.exit_price),
      reason: row.exit_reason, net_usdt: row.net_pnl_usdt,
      pnl_percent: String(Number(row.net_pnl_usdt) / 10),
    });
  }
  events.push({
    source: "SIMULATION", simulation_run_id: id,
    kind: "CANDLE_CLOSED", sequence: events.length + 1, time_ms: t + 300_000,
    candle: { start_ms: t, end_ms: t + 300_000, open: 100, high: 103,
      low: 99, close: 101, volume: 1000 },
  });
  return {
    state: "VIRTUAL_L2_PROBE_CONDITIONAL",
    scenario: "ONE_BOUNDED_LOCAL_SIMULATION_NOT_REAL_BYBIT_EXECUTIONS",
    code_sha: "389e175c542d8319d245b70357d5e27c50e6f8e6",
    l2_sha256: BOOK_SHA, trade_gzip_sha256: TRADE_SHA,
    result: {
      symbol: "ICNTUSDT",
      execution_model: "SIMULATION_HISTORICAL_TAKER_L2_EVENT_TIME_NOT_REAL_BYBIT_FILLS",
      l2_source_sha256: BOOK_SHA, final_position_quantity: "0",
      virtual_fills: 8, realized_net_pnl: "5.2", l2_episodes: orders,
      replay: {
        source: "SIMULATION", simulation_run_id: id, symbol: "ICNTUSDT",
        mode: "STRATEGY", timeframe: "5m", demo: false,
        market_data_source: "PINNED_BYBIT_PUBLIC_TRADES_PLUS_L2_EVENT_TIME_SIMULATION",
        execution_clock: "ORIGINAL_EVENT_TIME_NOT_OHLC_M1",
        execution_certainty: "CONDITIONAL_L2_NOT_REAL_EXCHANGE_FILLS",
        partial_and_be_markers: "EVENTS_ONLY_CONDITIONAL",
        events,
      },
    },
  };
};

describe("one-click original owner ICNT L2 report import", () => {
  it("uses existing owner JSON without repeating the simulation or fabricating candles", () => {
    const raw = output();
    const doc = parseLocalReplayUpload(raw);
    expect(doc.events).toHaveLength(9);
    expect(doc.execution_certainty).toBe("CONDITIONAL_L2_NOT_REAL_EXCHANGE_FILLS");
    expect(doc.events.filter(e => e.kind === "ENTRY_FILLED").map(e => e.quantity))
      .toEqual(["10", "10", "10", "10"]);
    expect(doc.events.filter(e => e.kind === "EXIT_FILLED").map(e => e.fee_usdt))
      .toEqual(["0.6", "0.6", "0.6", "0.6"]);
    const shown = visibleReplay(doc.events, doc.events.length);
    expect(visibleExecutionMarkers(doc.events, shown.candles)).toHaveLength(8);
    expect(simulationActionJournal(doc).actions).toHaveLength(8);
    expect(parseLocalReplayUpload(doc).events).toEqual(doc.events);
  });

  it("rejects altered profits, unknown fills, unsupported source and wrong chronology", () => {
    const reject = (modify: (value: ReturnType<typeof output>) => void) => {
      const value = output();
      modify(value);
      expect(() => parseLocalReplayUpload(value)).toThrow();
    };
    reject(x => { x.trade_gzip_sha256 = "0".repeat(64); });
    reject(x => { x.result.realized_net_pnl = "5.3"; });
    reject(x => { x.result.l2_episodes[0].entry_ms++; });
    reject(x => { x.result.l2_episodes[0].entry_fee = "500"; });
    reject(x => { x.result.l2_episodes[3].partial_quantity = "2" as never; });
    reject(x => { x.result.replay.events[0].price = 200; });
    reject(x => { x.result.replay.events[0].trade_id = "SIMULATION:other:wrong"; });
    reject(x => { x.result.replay.events.splice(1, 1); });
  });

  it("retains strict direct JSON route with no envelope", () => {
    const doc = parseLocalReplayUpload(output());
    expect(parseLocalReplayUpload(doc)).toEqual(doc);
  });
});
