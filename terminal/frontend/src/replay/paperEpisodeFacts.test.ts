import { describe, expect, it } from "vitest";
import { parseReplayDocument, type ReplayDocument } from "./replayModel";
import { isReplayUsdtSymbol, parseRunCoordinates, makeWedgeRunRequest, onlyWedges, parseWedgeStatus } from "./runSetup";
import {
  matchPaperFactsToMarket, parsePaperEpisodeFacts, revealedPaperMarkers, visibleGeometryRevisions, visiblePaperExecutionCounts, visibleBoxPlan,
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
  it("accepts the exact short ticker through facts, history, coordinates and marker matching", () => {
    for (const symbol of ["SUSDT", "WUSDT", "ARUSDT", "BTCUSDT", "1000000MOGUSDT", "A".repeat(26) + "USDT"]) {
      const facts = parsePaperEpisodeFacts({ ...source, symbol });
      const history = parseReplayDocument(market(symbol));
      expect(facts.symbol).toBe(symbol);
      expect(history.symbol).toBe(symbol);
      expect(parseReplayDocument({ ...market(symbol), mode: "STRATEGY",
        market_data_source: "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M" }).symbol).toBe(symbol);
      expect(matchPaperFactsToMarket(facts, history).markers).toHaveLength(2);
      const start = "2026-10-01T00:00", end = "2026-10-01T23:59";
      expect(parseRunCoordinates(symbol + " | " + start + " | " + end).symbol).toBe(symbol);
      expect(makeWedgeRunRequest(onlyWedges(), symbol, start, end, "1000").symbol).toBe(symbol);
      expect(parseWedgeStatus({
        namespace: "SIMULATION", can_attempt: false, wedge_engine_available: true,
        python_dependencies_available: true, archive_files_present: true,
        wedge_risk_profile_present: false,
        archive_hint: { symbol, start_utc: start, end_utc_inclusive: end },
      }).archive_hint?.symbol).toBe(symbol);
    }
    for (const symbol of ["USDT", "SUSDC", "S/USDT", "sUSDT", "SUSDT\n", "A".repeat(27) + "USDT"]) {
      expect(isReplayUsdtSymbol(symbol)).toBe(false);
      expect(() => parsePaperEpisodeFacts({ ...source, symbol })).toThrow();
      // Generic MARKET_ONLY archives retain their existing broader contract.
      expect(() => parseReplayDocument({ ...market(symbol), mode: "STRATEGY",
        market_data_source: "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M" })).toThrow();
    }
    const facts = parsePaperEpisodeFacts({ ...source, symbol: "SUSDT" });
    expect(matchPaperFactsToMarket(facts, parseReplayDocument(market("WUSDT"))).status).toBe("WAIT_MARKET");
  });

  it("preserves exact execution prices and maps them only onto real closed M5", () => {
    const facts = parsePaperEpisodeFacts(source);
    const history = market();
    const original = JSON.stringify(history.events);
    expect(facts.pnl_usdt).toBe("-1.0");
    expect(facts.realized_price_pnl_usdt).toBe("-0.9");
    expect(facts.known_execution_fees_usdt).toBe("0.1");
    expect(facts.execution_allocations.map(item => item.allocated_fee)).toEqual(["0.05", "0.05"]);
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

  it("counts only causally revealed PAPER entry and exit allocations, including partials", () => {
    const facts = parsePaperEpisodeFacts(source);
    const doc = market();
    const overlay = matchPaperFactsToMarket(facts, doc);
    const candles = doc.events.map(event => event.candle!);
    expect(visiblePaperExecutionCounts(facts, overlay, [])).toEqual({ entries: 0, exits: 0 });
    expect(visiblePaperExecutionCounts(facts, overlay, candles.slice(0, 3))).toEqual({ entries: 1, exits: 0 });
    expect(visiblePaperExecutionCounts(facts, overlay, candles)).toEqual({ entries: 1, exits: 1 });
    const partials = { ...facts, execution_allocations: [
      ...facts.execution_allocations,
      { ...facts.execution_allocations[0], allocation_role: "INCREASE" as const },
      { ...facts.execution_allocations[1], allocation_role: "REDUCE" as const },
    ] };
    expect(visiblePaperExecutionCounts(partials, overlay, candles)).toEqual({ entries: 2, exits: 2 });
    expect(visiblePaperExecutionCounts(facts, matchPaperFactsToMarket(facts, market("ETHUSDT")), candles))
      .toEqual({ entries: 0, exits: 0 });
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


describe("PAPER mixed-controller cohorts match canonical Diary scope", () => {
  const [open, close] = source.execution_allocations;
  const mixed = (allocations: typeof source.execution_allocations,
                 cohort = "JOINT_MANAGEMENT", owner = "ROBOT") =>
    ({ ...source, cohort, owner, execution_allocations: allocations });
  const reduce = { ...close, execution_id: "exec-reduce", order_id: "order-reduce",
    allocation_role: "REDUCE", controller: "MANUAL", allocated_quantity: "1",
    occurred_at_ms: open.occurred_at_ms + 1000 };
  const increase = { ...open, execution_id: "exec-increase", order_id: "order-increase",
    allocation_role: "INCREASE", controller: "MANUAL", allocated_quantity: "1",
    occurred_at_ms: open.occurred_at_ms + 1000 };

  it("accepts manual opening and Robot close under both joint report scopes", () => {
    const rows = [{ ...open, controller: "MANUAL" }, close];
    for (const owner of ["ROBOT", "MANUAL"]) {
      const facts = parsePaperEpisodeFacts(mixed(rows, "JOINT_MANAGEMENT", owner));
      expect(facts.execution_allocations.map(a => a.controller)).toEqual(["MANUAL", "ROBOT"]);
      expect(facts.cohort).toBe("JOINT_MANAGEMENT");
    }
  });

  it("replays manual open and increase, then Robot increase and close", () => {
    const rows = [
      { ...open, controller: "MANUAL" },
      increase,
      { ...increase, execution_id: "exec-robot-add", order_id: "order-robot-add",
        controller: "ROBOT", occurred_at_ms: increase.occurred_at_ms + 1000 },
      { ...close, allocated_quantity: "4" },
    ];
    const facts = parsePaperEpisodeFacts(mixed(rows));
    expect(facts.execution_allocations).toEqual(rows);
    expect(matchPaperFactsToMarket(facts, market()).markers).toHaveLength(4);
  });

  it("accepts manual partial reduction or increase without changing the source executions", () => {
    for (const mid of [reduce, increase]) {
      const rows = [open, mid, { ...close,
        allocated_quantity: mid.allocation_role === "REDUCE" ? "1" : "3" }];
      const facts = parsePaperEpisodeFacts(mixed(rows));
      expect(facts.execution_allocations).toEqual(rows);
      expect(matchPaperFactsToMarket(facts, market()).markers).toHaveLength(3);
    }
  });

  it("accepts manual increase and manual final close as joint, not assisted", () => {
    const rows = [open, increase, { ...close, controller: "MANUAL", allocated_quantity: "3" }];
    expect(parsePaperEpisodeFacts(mixed(rows)).cohort).toBe("JOINT_MANAGEMENT");
    expect(() => parsePaperEpisodeFacts(mixed(rows, "ROBOT_MANUAL_CLOSE"))).toThrow();
  });

  it("rejects mislabeled autonomous, assisted, unknown and invalid intermediate lifecycle", () => {
    const assisted = [open, { ...close, controller: "MANUAL" }];
    expect(parsePaperEpisodeFacts(mixed(assisted, "ROBOT_MANUAL_CLOSE")).cohort)
      .toBe("ROBOT_MANUAL_CLOSE");
    for (const rows of [
      [open, close],
      assisted,
      [open, { ...reduce, controller: "EXTERNAL" }, close],
      [open, { ...increase, allocation_role: "OPEN" }, close],
    ]) expect(() => parsePaperEpisodeFacts(mixed(rows))).toThrow();
  });
});


describe("Exact Robot candidate archive independent of D2", () => {
  const d2 = { status: "D2_STORE_ABSENT", source: "TRADING_DIARY_D2",
    geometry_status: "NOT_EXPORTED", decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG" };
  const candidate = {
    verified_signal: {
      trade_episode_id: source.trade_episode_id, source_revision: source.source_revision,
      candidate_id: "candidate-42", pattern: "Falling Wedge", source_timeframe: "5m",
      status: "PROVEN", provenance: "DURABLE_ROBOT_TRADE_METADATA_NOT_ORIGINAL_GEOMETRY",
      evidence_scope: "EXACT_WEDGE_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE",
    },
    signal_time_ms: t + 300_000,
    geometry: { ...originalArchive, linkage_basis: "EXACT_ROBOT_CANDIDATE_ENTRY_ORDER_EXECUTION_EPISODE" },
  };
  it("preserves original boundaries and truthful D2 absence", () => {
    const imported = parsePaperEpisodeFacts({ ...source, setup_context: d2, candidate_geometry: candidate });
    expect(imported.setup_context?.status).toBe("D2_STORE_ABSENT");
    expect(imported.candidate_geometry?.geometry.boundaries[0].anchors)
      .toEqual(originalArchive.snapshot.boundaries[0].anchors);
    expect(imported.candidate_geometry?.pattern).toBe("Falling Wedge");
  });
  it("rejects mismatched revision, episode, candidate, timeframe, future time and conflicting D2", () => {
    for (const patch of [
      { source_revision: 4 }, { trade_episode_id: "te_" + "b".repeat(24) },
      { candidate_id: "other" }, { source_timeframe: "1m" }, { status: "UNPROVEN" },
    ]) expect(() => parsePaperEpisodeFacts({ ...source, setup_context: d2,
      candidate_geometry: { ...candidate, verified_signal: { ...candidate.verified_signal, ...patch } },
    })).toThrow();
    expect(() => parsePaperEpisodeFacts({ ...source, setup_context: d2,
      candidate_geometry: { ...candidate, signal_time_ms: originalArchive.sent_at_ms + 1 },
    })).toThrow();
    expect(() => parsePaperEpisodeFacts({ ...source, setup_context: { ...d2, status: "CONFLICTING_D2_LINK" },
      candidate_geometry: candidate,
    })).toThrow();
  });
});


describe("Recorded wedge revisions", () => {
  it("reveals only causal observations and rejects a conflicting chain without hiding fills", () => {
    const old = { boundary_id: "upper", kind: "ray", anchors: [
      {bar_open_time_ms:t,price:102},{bar_open_time_ms:t+300000,price:101},
    ]};
    const current = { ...old, anchors: [old.anchors[0],{bar_open_time_ms:t+600000,price:101}] };
    const at = t+900001;
    const d2 = { ...linkedD2, geometry_status:"ORIGINAL_ARCHIVE_HASH_VERIFIED",
      original_geometry:{ ...originalArchive,snapshot:{...originalArchive.snapshot,boundaries:[old]}} };
    const event = { revision:1, event:"Паттерн перестроен", event_time_ms:at,
      candidate_id:"candidate-42",source_geometry_sha256:"a".repeat(64),family:"falling",
      source_trade_id:"print-1",reason:"CONTROL_CONTACT",previous_extreme:"98",
      trigger_price:"97.99",previous_boundary:old,current_boundary:current };
    const payload = { schema:"BYBITSCANNER_WEDGE_GEOMETRY_REVISIONS_V1",
      source:"ROBOT_OBSERVED_PUBLIC_TRADES",coverage:"LOCAL_OBSERVATION_NOT_COMPLETE_EXCHANGE_TAPE",
      candidate_id:"candidate-42",source_geometry_sha256:"a".repeat(64),events:[event] };
    const facts = parsePaperEpisodeFacts({...source,setup_context:d2,geometry_revisions:payload});
    expect(visibleGeometryRevisions(facts,at-1)).toEqual([]);
    expect(visibleGeometryRevisions(facts,at)[0].current_boundary).toEqual(current);
    expect(visibleGeometryRevisions(facts,at)[0].previous_boundary).toEqual(old);
    expect(visibleGeometryRevisions(facts,at-1)).toEqual([]); // rewind
    const broken = parsePaperEpisodeFacts({...source,setup_context:d2,
      geometry_revisions:{...payload,events:[{...event,previous_boundary:current}]}});
    expect(broken.geometry_revisions).toBeUndefined();
    expect(broken.execution_allocations).toHaveLength(2);
  });
});


it("shows only verified saved Box plan after its decision, without converting plans to executions", () => {
  const d2 = { status: "NO_EXACT_EPISODE_LINK", source: "TRADING_DIARY_D2",
    geometry_status: "NOT_EXPORTED", decision_scope: "D2_OBSERVATIONS_NOT_ROBOT_RUNTIME_LOG" };
  const box = {
    schema: "BYBITSCANNER_FROZEN_BOX_PLAN_GEOMETRY_V1",
    source: "VERIFIED_DURABLE_BOX_PLAN_NOT_ORIGINAL_ARCHIVE",
    trade_episode_id: source.trade_episode_id, source_revision: source.source_revision,
    source_candidate_id: "box-plan-" + "a".repeat(64), robot_candidate_id: "box-robot-" + "a".repeat(64),
    source_snapshot_sha256: "b".repeat(64), symbol: source.symbol, side: source.side, timeframe: "5",
    a_time_ms: t, b_time_ms: t + 300000, decision_time_ms: t + 600000,
    anchors: { a_price: "112", b_price: "100" },
    fibonacci: { f1: "100", f1618: "92", f2618: "79" },
    limit_prices: ["94", "93.2", "92.4", "91.6"],
  };
  const facts = parsePaperEpisodeFacts({ ...source, setup_context: d2, box_plan_geometry: box });
  const overlay = matchPaperFactsToMarket(facts, market());
  expect(facts.box_plan_geometry?.fibonacci.f1618).toBe("92");
  expect(visibleBoxPlan(facts, overlay, box.decision_time_ms - 1)).toBeUndefined();
  expect(visibleBoxPlan(facts, overlay, box.decision_time_ms)).toEqual(facts.box_plan_geometry);
  expect(visibleBoxPlan(facts, matchPaperFactsToMarket(facts, market("ETHUSDT")), box.decision_time_ms)).toBeUndefined();
  for (const patch of [{ source_revision: 99 }, { robot_candidate_id: "foreign" },
    { decision_time_ms: source.opened_at_ms + 1 }, { limit_prices: ["94"] }]) {
    const bad = parsePaperEpisodeFacts({ ...source, setup_context: d2, box_plan_geometry: { ...box, ...patch } });
    expect(bad.box_plan_geometry).toBeUndefined();
    expect(bad.execution_allocations).toEqual(facts.execution_allocations);
  }
});
