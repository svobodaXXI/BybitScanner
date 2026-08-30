import { describe, expect, it } from "vitest";
import type { MarketDataSnapshot } from "../contracts/marketData";
import { applyWorkspaceEvent, type WorkspaceProjectionState } from "./workspaceProjection";

const emptySnapshot = (): MarketDataSnapshot => ({
  book: { symbol: "OLDUSDT", bids: [], asks: [], health: "NOT_READY", receivedAt: "", availableDepth: 0 },
  candles: [], tickSize: null, trades: [], ownOrders: [], source: "DEVELOPMENT",
});

const snapshotEvent = (overrides: Record<string, unknown> = {}) => ({
  stream_id: "stream-1",
  event_sequence: 1,
  event_timestamp: 1000,
  symbol: "BTCUSDT",
  workspace_generation: 7,
  kind: "workspace_snapshot",
  state: "READY",
  instrument: { symbol: "BTCUSDT", tick_size: "0.5", quantity_step: "0.001" },
  book: {
    kind: "book_snapshot", state: "READY", projection_version: 3,
    source_timestamp: 1000, upstream_update_id: 10, upstream_sequence: 20,
    bids: [{ price: "100", size: "2" }], asks: [{ price: "101", size: "3" }],
  },
  trades: { kind: "trade_bootstrap", state: "READY", projection_version: 1, trades: [] },
  candles: {
    kind: "candle_bootstrap", state: "READY", interval: "5", projection_version: 1,
    candles: [{ startTime: 1000, open: "1", high: "2", low: "1", close: "1.5" }],
  },
  ...overrides,
});

const initial = (): WorkspaceProjectionState => ({ authority: null, snapshot: emptySnapshot() });

describe("atomic Workspace projection", () => {
  it("applies one complete workspace_snapshot atomically", () => {
    const result = applyWorkspaceEvent(initial(), snapshotEvent(), "BTCUSDT", "5", 2000);
    expect(result.decision).toBe("APPLIED");
    expect(result.state.authority).toEqual({
      streamId: "stream-1", symbol: "BTCUSDT", generation: 7,
      eventSequence: 1, interval: "5", state: "READY",
    });
    expect(result.state.snapshot.book.symbol).toBe("BTCUSDT");
    expect(result.state.snapshot.book.bookVersion).toBe(3);
    expect(result.state.snapshot.candles).toHaveLength(1);
    expect(result.state.snapshot.tickSize).toBe(0.5);
    expect(result.state.snapshot.trades).toEqual([]);
  });

  it("rejects an incomplete snapshot without partially replacing old state", () => {
    const before = initial();
    const event = snapshotEvent({ candles: { kind: "candle_bootstrap", state: "READY", interval: "5", candles: [] } });
    const result = applyWorkspaceEvent(before, event, "BTCUSDT", "5");
    expect(result.decision).toBe("RESNAPSHOT_REQUIRED");
    expect(result.state).toBe(before);
  });

  it("ignores wrong generation and requires resnapshot for gaps and regressions", () => {
    const ready = applyWorkspaceEvent(initial(), snapshotEvent(), "BTCUSDT", "5").state;
    const wrongGeneration = applyWorkspaceEvent(ready, {
      stream_id: "stream-1", event_sequence: 2, symbol: "BTCUSDT",
      workspace_generation: 6, kind: "health", state: "READY", component: "stream", payload: {},
    }, "BTCUSDT", "5");
    expect(wrongGeneration.decision).toBe("IGNORED_STALE");
    expect(wrongGeneration.state).toBe(ready);

    const gap = applyWorkspaceEvent(ready, {
      stream_id: "stream-1", event_sequence: 3, symbol: "BTCUSDT",
      workspace_generation: 7, kind: "health", state: "READY", component: "stream", payload: {},
    }, "BTCUSDT", "5");
    expect(gap.decision).toBe("RESNAPSHOT_REQUIRED");

    const regression = applyWorkspaceEvent(ready, {
      stream_id: "stream-1", event_sequence: 0, symbol: "BTCUSDT",
      workspace_generation: 7, kind: "health", state: "READY", component: "stream", payload: {},
    }, "BTCUSDT", "5");
    expect(regression.decision).toBe("RESNAPSHOT_REQUIRED");

    const staleSymbol = applyWorkspaceEvent(ready, {
      stream_id: "stream-1", event_sequence: 2, symbol: "BTCUSDT",
      workspace_generation: 7, kind: "health", state: "READY", component: "stream", payload: {},
    }, "ETHUSDT", "5");
    expect(staleSymbol.decision).toBe("IGNORED_STALE");

    const snapshotRegression = applyWorkspaceEvent(ready, snapshotEvent({ event_sequence: 0 }), "BTCUSDT", "5");
    expect(snapshotRegression.decision).toBe("RESNAPSHOT_REQUIRED");
  });

  it("does not let a transport heartbeat restore degraded Workspace authority", () => {
    const ready = applyWorkspaceEvent(initial(), snapshotEvent(), "BTCUSDT", "5").state;
    const degraded = applyWorkspaceEvent(ready, {
      stream_id: "stream-1", event_sequence: 2, symbol: "BTCUSDT",
      workspace_generation: 7, kind: "health", state: "DEGRADED", component: "book", payload: {},
    }, "BTCUSDT", "5").state;
    expect(degraded.authority?.state).toBe("DEGRADED");
    expect(degraded.snapshot.book.health).toBe("DEGRADED");
    const heartbeat = applyWorkspaceEvent(degraded, {
      stream_id: "stream-1", event_sequence: 3, symbol: "BTCUSDT",
      workspace_generation: 7, kind: "health", state: "READY", component: "stream",
      payload: { service_alive: true },
    }, "BTCUSDT", "5");
    expect(heartbeat.decision).toBe("APPLIED");
    expect(heartbeat.state.authority?.state).toBe("DEGRADED");
    expect(heartbeat.state.snapshot.book.health).toBe("DEGRADED");
  });

  it("applies sequenced book deltas and rejects a base-version mismatch", () => {
    const ready = applyWorkspaceEvent(initial(), snapshotEvent(), "BTCUSDT", "5").state;
    const delta = {
      stream_id: "stream-1", event_sequence: 2, symbol: "BTCUSDT",
      workspace_generation: 7, kind: "book_delta", state: "READY", component: "book",
      payload: {
        base_version: 3, new_version: 4, upstream_update_id: 11, upstream_sequence: 21,
        bids: [{ price: "100", size: "4" }], asks: [{ price: "102", size: "1" }, { price: "101", size: "0" }],
      },
    };
    const applied = applyWorkspaceEvent(ready, delta, "BTCUSDT", "5");
    expect(applied.decision).toBe("APPLIED");
    expect(applied.state.snapshot.book.bids[0].quantity).toBe(4);
    expect(applied.state.snapshot.book.asks[0].price).toBe(102);
    expect(applied.state.snapshot.book.bookVersion).toBe(4);

    const mismatch = applyWorkspaceEvent(ready, {
      ...delta, payload: { ...delta.payload, base_version: 2 },
    }, "BTCUSDT", "5");
    expect(mismatch.decision).toBe("RESNAPSHOT_REQUIRED");
    expect(mismatch.state).toBe(ready);
  });
});
