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


const linkedD2 = {
  status: "EXACT_D2_LINK", source: "TRADING_DIARY_D2",
  consistency: "INDEPENDENT_READ_SNAPSHOT_NOT_ATOMIC_WITH_PAPER",
  geometry_status: "NOT_EXPORTED",
  decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
  setup: {
    setup_instance_id: "setup-1", setup_id: "candidate-42", symbol: "BTCUSDT",
    direction: "LONG", timeframe: "5m", pattern: "Falling Wedge",
    strategy_version: "v1", entry_mode: "breakout_retest",
    origin: "ROBOT", created_at_ms: t + 300_000, has_feature_snapshot_ref: true,
  },
  order_plan_id: "plan-1", linked_at_ms: t + 330_000,
  decisions: [
    { decision_event_id: "strategy-1", kind: "STRATEGY", previous_state: null,
      next_state: "APPROVED", reason_code: "STRATEGY_OK", controller: "ROBOT",
      origin: "ROBOT", occurred_at_ms: t + 301_000 },
    { decision_event_id: "risk-1", kind: "RISK", previous_state: "APPROVED",
      next_state: "APPROVED", reason_code: "RISK_OK", controller: "ROBOT",
      origin: "ROBOT", occurred_at_ms: t + 302_000 },
  ],
};


const originalArchive = {
  schema: "BYBITSCANNER_ARCHIVED_SIGNAL_GEOMETRY_V1",
  source: "ORIGINAL_TELEGRAM_SIGNAL_ARCHIVE",
  linkage_basis: "D2_SETUP_ID_EQUALS_ARCHIVED_CANDIDATE_ID",
  integrity: "LOCAL_ARCHIVE_HASH_ONLY_NOT_CRYPTOGRAPHIC_PROOF",
  signal_id: "candidate-42", sent_at_ms: t + 350_000, sha256: "a".repeat(64),
  snapshot: {
    schema_version: 1, signal_id: "candidate-42", symbol: "BTCUSDT", timeframe: "5m",
    bars: [
      { open_time_ms: t, open: 100, high: 102, low: 98, close: 101 },
      { open_time_ms: t + 300_000, open: 101, high: 103, low: 100, close: 102 },
    ],
    boundaries: [
      { boundary_id: "lower", kind: "segment", anchors: [
        { bar_open_time_ms: t, price: 99 },
        { bar_open_time_ms: t + 300_000, price: 100 },
      ] },
    ],
  },
};

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

  it("reads exact D2 setup and decision observations as optional non-executable context", () => {
    const imported = parsePaperEpisodeFacts({ ...source, setup_context: linkedD2 });
    expect(imported.setup_context?.status).toBe("EXACT_D2_LINK");
    if (imported.setup_context?.status !== "EXACT_D2_LINK") throw new Error("missing D2");
    expect(imported.setup_context.setup.setup_id).toBe("candidate-42");
    expect(imported.setup_context.setup.timeframe).toBe("5m");
    expect(imported.setup_context.decisions.map(e => e.reason_code))
      .toEqual(["STRATEGY_OK", "RISK_OK"]);
    expect(imported.setup_context.geometry_status).toBe("NOT_EXPORTED");
    expect(imported.execution_allocations).toHaveLength(2); // never mixed with D2.
    expect(parsePaperEpisodeFacts(source).setup_context).toBeUndefined();
    const missing = parsePaperEpisodeFacts({ ...source, setup_context: {
      status: "NO_EXACT_EPISODE_LINK", source: "TRADING_DIARY_D2",
      geometry_status: "NOT_EXPORTED", decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
    } });
    expect(missing.setup_context?.status).toBe("NO_EXACT_EPISODE_LINK");
  });

  it("parses only exact archived frozen geometry separately from virtual candle geometry", () => {
    const sourceD2 = {
      ...linkedD2, geometry_status: "ORIGINAL_ARCHIVE_HASH_VERIFIED",
      original_geometry: originalArchive,
    };
    const imported = parsePaperEpisodeFacts({ ...source, setup_context: sourceD2 });
    expect(imported.setup_context?.geometry_status).toBe("ORIGINAL_ARCHIVE_HASH_VERIFIED");
    if (imported.setup_context?.status !== "EXACT_D2_LINK") throw new Error("missing D2");
    expect(imported.setup_context.original_geometry?.boundaries[0].anchors).toEqual([
      { bar_open_time_ms: t, price: 99 },
      { bar_open_time_ms: t + 300_000, price: 100 },
    ]);
    const history = market();
    const events = JSON.stringify(history.events);
    expect(matchPaperFactsToMarket(imported, history).status).toBe("MATCHED");
    expect(JSON.stringify(history.events)).toBe(events); // no simulated strategy mutation
  });

  it("rejects unlinked, mismatched, future and corrupted original source geometry", () => {
    const d2 = {
      ...linkedD2, geometry_status: "ORIGINAL_ARCHIVE_HASH_VERIFIED",
      original_geometry: originalArchive,
    };
    for (const invalid of [
      { ...d2, original_geometry: { ...originalArchive, signal_id: "different" } },
      { ...d2, original_geometry: { ...originalArchive, sent_at_ms: source.closed_at_ms + 1 } },
      { ...d2, original_geometry: { ...originalArchive, sha256: "garbage" } },
      { ...d2, original_geometry: { ...originalArchive, snapshot: {
        ...originalArchive.snapshot, symbol: "ETHUSDT",
      } } },
      { ...d2, original_geometry: { ...originalArchive, snapshot: {
        ...originalArchive.snapshot, boundaries: [{
          boundary_id: "bad", kind: "ray", anchors: [
            { bar_open_time_ms: t + 90_000, price: 99 },
            { bar_open_time_ms: t + 300_000, price: 100 },
          ],
        }],
      } } },
      { ...d2, original_geometry: undefined },
      { ...linkedD2, original_geometry: originalArchive },
      { status: "NO_EXACT_EPISODE_LINK", source: "TRADING_DIARY_D2",
        geometry_status: "ORIGINAL_ARCHIVE_HASH_VERIFIED",
        decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG",
        original_geometry: originalArchive },
    ]) expect(() => parsePaperEpisodeFacts({ ...source, setup_context: invalid })).toThrow();
  });

  it("rejects contradictory, unauthenticated or future-leaking D2 claims", () => {
    for (const invalid of [
      { ...linkedD2, status: "NO_EXACT_EPISODE_LINK" },
      { ...linkedD2, geometry_status: "FULL_SNAPSHOT" },
      { ...linkedD2, consistency: "ATOMIC_WITH_PAPER" },
      { ...linkedD2, setup: { ...linkedD2.setup, symbol: "ETHUSDT" } },
      { ...linkedD2, setup: { ...linkedD2.setup, origin: "TERMINAL_MANUAL" } },
      { ...linkedD2, decisions: linkedD2.decisions.slice(0, 1) },
      { ...linkedD2, decisions: [linkedD2.decisions[1], linkedD2.decisions[0]] },
      { ...linkedD2, decisions: [
        linkedD2.decisions[0], { ...linkedD2.decisions[1], reason_code: "" },
      ] },
    ]) expect(() => parsePaperEpisodeFacts({ ...source, setup_context: invalid })).toThrow();
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
