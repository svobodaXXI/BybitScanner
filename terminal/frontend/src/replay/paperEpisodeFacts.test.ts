import { describe, expect, it } from "vitest";
import type { ReplayDocument } from "./replayModel";
import {
  matchPaperFactsToMarket, parsePaperEpisodeFacts, revealedPaperMarkers,
} from "./paperEpisodeFacts";

const t = Date.UTC(2026, 9, 1);
const source = {
  ok: true, schema: "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1",
  namespace: "PAPER_READ_ONLY", source: "PAPER_EXECUTIONS_ATTRIBUTED",
  source_revision: 3, account_id: "paper", owner: "ROBOT", cohort: "ROBOT",
  trade_episode_id: "te_" + "a".repeat(24), symbol: "BTCUSDT", side: "LONG",
  opened_at_ms: t + 2 * 300000 + 2000,
  closed_at_ms: t + 7 * 300000 + 2000,
  realized_price_pnl_usdt: "-0.9", known_execution_fees_usdt: "0.1",
  pnl_usdt: "-1.0", pnl_basis: "REALIZED_PRICE_MINUS_EXECUTION_FEES",
  replay_evidence: "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES",
  execution_allocations: [
    { execution_id: "exec-1", order_id: "order-1", order_side: "Buy",
      execution_price: "100.12345678", allocated_quantity: "2", allocated_fee: "0.05",
      occurred_at_ms: t + 2 * 300000 + 2000, allocation_role: "OPEN", controller: "ROBOT" },
    { execution_id: "exec-2", order_id: "order-2", order_side: "Sell",
      execution_price: "99.5", allocated_quantity: "2", allocated_fee: "0.05",
      occurred_at_ms: t + 7 * 300000 + 2000, allocation_role: "CLOSE", controller: "ROBOT" },
  ],
};
const market = (symbol = "BTCUSDT", length = 10): ReplayDocument => ({
  source: "SIMULATION", simulation_run_id: "market_only_history",
  mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE", symbol, timeframe: "5m",
  events: Array.from({ length }, (_, index) => ({
    source: "SIMULATION", simulation_run_id: "market_only_history",
    sequence: index + 1, kind: "CANDLE_CLOSED", time_ms: t + (index + 1) * 300000,
    candle: { start_ms: t + index * 300000, end_ms: t + (index + 1) * 300000,
      open: 100, high: 102, low: 98, close: 101, volume: 30 },
  })),
});

describe("PAPER episode facts are display-only, never SIMULATION fills", () => {
  it("preserves exact execution prices and maps them only onto real closed M5", () => {
    const facts = parsePaperEpisodeFacts(source);
    const history = market();
    const original = JSON.stringify(history.events);
    expect(facts.pnl_usdt).toBe("-1.0");
    expect(facts.execution_allocations[0].execution_price).toBe("100.12345678");
    const overlay = matchPaperFactsToMarket(facts, history);
    expect(overlay.status).toBe("MATCHED");
    expect(overlay.markers).toHaveLength(2);
    expect(overlay.markers.map(item => item.candle_start_ms)).toEqual([
      t + 2 * 300000, t + 7 * 300000,
    ]);
    expect(overlay.markers.map(item => item.order_side)).toEqual(["Buy", "Sell"]);
    expect(revealedPaperMarkers(overlay, [
      history.events[0].candle!, history.events[1].candle!,
      history.events[2].candle!,
    ])).toHaveLength(1);
    expect(revealedPaperMarkers(overlay, [])).toEqual([]);
    expect(JSON.stringify(history.events)).toBe(original); // never modify the simulation
  });

  it("maps exact M5-boundary executions to the next fully closed bar, not the past", () => {
    const changed = {
      ...source, opened_at_ms: t + 2 * 300000,
      execution_allocations: [
        { ...source.execution_allocations[0], occurred_at_ms: t + 2 * 300000 },
        source.execution_allocations[1],
      ],
    };
    const parsed = parsePaperEpisodeFacts(changed);
    const doc = market();
    const overlay = matchPaperFactsToMarket(parsed, doc);
    expect(overlay.status).toBe("MATCHED");
    expect(overlay.markers[0].candle_start_ms).toBe(t + 2 * 300000);
    expect(revealedPaperMarkers(overlay, doc.events.slice(0, 2).map(x => x.candle!))).toEqual([]);
    expect(revealedPaperMarkers(overlay, doc.events.slice(0, 3).map(x => x.candle!))).toHaveLength(1);
  });

  it("fails closed when ticker, source, candle coverage or history provenance mismatch", () => {
    const facts = parsePaperEpisodeFacts(source);
    expect(matchPaperFactsToMarket(facts, market("ETHUSDT")).status).toBe("WAIT_MARKET");
    expect(matchPaperFactsToMarket(facts, market("BTCUSDT", 4)).markers).toEqual([]);
    expect(matchPaperFactsToMarket(facts, { ...market(), demo: true }).markers).toEqual([]);
    expect(matchPaperFactsToMarket(facts, {
      ...market(), market_data_source: undefined,
    }).markers).toEqual([]);
    expect(matchPaperFactsToMarket(facts, {
      ...market(), mode: "STRATEGY",
    }).markers).toEqual([]);
    const withGap = market();
    withGap.events.splice(2, 1);
    expect(matchPaperFactsToMarket(facts, withGap).markers).toEqual([]);
  });

  it("rejects imported simulated, MAIN, forged controller and unproven execution facts", () => {
    for (const patch of [
      { namespace: "SIMULATION" }, { account_id: "bybit-main" },
      { replay_evidence: "FULL_REPLAY" }, { trade_episode_id: "random" },
      { cohort: "MANUAL" }, { pnl_usdt: "4" },
    ]) expect(() => parsePaperEpisodeFacts({ ...source, ...patch })).toThrow();
    for (const patch of [
      { order_side: "Sell" }, { execution_price: "NaN" },
      { allocated_quantity: "0" }, { controller: "MANUAL" },
      { occurred_at_ms: source.opened_at_ms - 1000 },
    ]) expect(() => parsePaperEpisodeFacts({
      ...source, execution_allocations: [{ ...source.execution_allocations[0], ...patch },
        source.execution_allocations[1]],
    })).toThrow();
    expect(() => parsePaperEpisodeFacts({
      ...source, execution_allocations: [source.execution_allocations[0]],
    })).toThrow();
  });

  it("accepts scientific Decimal text without changing the original amount", () => {
    const exported = { ...source,
      realized_price_pnl_usdt: "0E-8", known_execution_fees_usdt: "0E-8",
      pnl_usdt: "0E-8",
      execution_allocations: source.execution_allocations.map(a => ({ ...a, allocated_fee: "0E-8" })),
    };
    const facts = parsePaperEpisodeFacts(exported);
    expect(facts.pnl_usdt).toBe("0E-8");
    expect(facts.execution_allocations[0].allocated_fee).toBe("0E-8");
  });
});
