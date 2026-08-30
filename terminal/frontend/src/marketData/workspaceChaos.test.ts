import { afterEach, describe, expect, it, vi } from "vitest";
import type { MarketDataSnapshot } from "../contracts/marketData";
import { applyWorkspaceEvent, type WorkspaceProjectionState } from "./workspaceProjection";
import { BackendWorkspaceMarketDataStore } from "./workspaceMarketDataStore";

const empty = (): WorkspaceProjectionState => ({
  authority: null,
  snapshot: {
    book: { symbol: "OLDUSDT", bids: [], asks: [], health: "NOT_READY", receivedAt: "", availableDepth: 0 },
    candles: [], tickSize: null, trades: [], ownOrders: [], source: "DEVELOPMENT",
  } satisfies MarketDataSnapshot,
});

const snapshot = (overrides: Record<string, unknown> = {}) => ({
  stream_id: "stream-7", event_sequence: 1, event_timestamp: 1000,
  symbol: "BTCUSDT", workspace_generation: 7, kind: "workspace_snapshot", state: "READY",
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

const sequenced = (kind: string, event_sequence: number, overrides: Record<string, unknown> = {}) => ({
  stream_id: "stream-7", event_sequence, symbol: "BTCUSDT", workspace_generation: 7,
  kind, state: "READY", component: "stream", payload: {}, ...overrides,
});

const trade = (id: string, endedAt: number) => ({
  id, symbol: "BTCUSDT", side: "BUY", total_quantity: "2", total_notional_usdt: "201",
  first_execution_price: "100", last_execution_price: "101", sweep_low_price: "100",
  sweep_high_price: "101", tick_size: "0.5", trade_count: 2, swept_ticks: 2,
  swept_price_range: "1", started_at_ms: endedAt - 1, ended_at_ms: endedAt,
  first_trade_seq: endedAt, last_trade_seq: endedAt + 1,
  backend_first_received_at_ms: endedAt, backend_last_received_at_ms: endedAt + 1,
  finalized_at_ms: endedAt + 2, book_correlation: null,
});

class FakeSocket {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;
  constructor(readonly url: string) {}
  close() { this.closed = true; }
  message(payload: unknown) { this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent); }
  malformed() { this.onmessage?.({ data: "{" } as MessageEvent); }
  disconnect() { this.onclose?.(); }
}

afterEach(() => vi.useRealTimers());

describe("M7 Workspace authority and sequence chaos", () => {
  it("ignores stale, future, foreign, symbol, and interval authority", () => {
    const ready = applyWorkspaceEvent(empty(), snapshot(), "BTCUSDT", "5").state;
    for (const event of [
      sequenced("health", 2, { workspace_generation: 6 }),
      sequenced("health", 2, { workspace_generation: 8 }),
      sequenced("health", 2, { stream_id: "foreign" }),
      sequenced("health", 2, { symbol: "ETHUSDT" }),
    ]) {
      const result = applyWorkspaceEvent(ready, event, "BTCUSDT", "5");
      expect(result.decision).toBe("IGNORED_STALE");
      expect(result.state).toBe(ready);
    }
    expect(applyWorkspaceEvent(ready, sequenced("health", 2), "BTCUSDT", "1").decision)
      .toBe("IGNORED_STALE");
  });

  it("handles duplicate, gap, regression, unknown, and malformed boundaries", () => {
    const ready = applyWorkspaceEvent(empty(), snapshot(), "BTCUSDT", "5").state;
    expect(applyWorkspaceEvent(ready, sequenced("health", 1), "BTCUSDT", "5").decision)
      .toBe("IGNORED_STALE");
    for (const event of [sequenced("health", 3), sequenced("health", 0), sequenced("mystery", 2), null]) {
      expect(applyWorkspaceEvent(ready, event, "BTCUSDT", "5").decision)
        .toBe("RESNAPSHOT_REQUIRED");
    }
  });

  it("accepts recovery only through a complete authoritative snapshot", () => {
    const before = applyWorkspaceEvent(empty(), snapshot(), "BTCUSDT", "5").state;
    const malformed = snapshot({
      event_sequence: 2,
      book: { kind: "book_snapshot", state: "READY", projection_version: 4, bids: [], asks: [] },
    });
    const rejected = applyWorkspaceEvent(before, malformed, "BTCUSDT", "5");
    expect(rejected.decision).toBe("RESNAPSHOT_REQUIRED");
    expect(rejected.state).toBe(before);
    const recovered = applyWorkspaceEvent(before, snapshot({ stream_id: "stream-8", workspace_generation: 8 }), "BTCUSDT", "5");
    expect(recovered.decision).toBe("APPLIED");
    expect(recovered.state.authority?.streamId).toBe("stream-8");
    expect(recovered.state.authority?.generation).toBe(8);
  });
});

describe("M7 Workspace projection churn", () => {
  it("applies displacement/reveal, deduplicated trades, and candle replace/append atomically", () => {
    let state = applyWorkspaceEvent(empty(), snapshot(), "BTCUSDT", "5").state;
    const book = applyWorkspaceEvent(state, sequenced("book_delta", 2, {
      component: "book", payload: {
        base_version: 3, new_version: 4, upstream_update_id: 11, upstream_sequence: 21,
        bids: [{ price: "100", size: "0" }, { price: "99", size: "5" }], asks: [{ price: "102", size: "1" }],
      },
    }), "BTCUSDT", "5");
    expect(book.decision).toBe("APPLIED");
    expect(book.state.snapshot.book.bids.map((level) => level.price)).toEqual([99]);
    state = book.state;

    const trades = applyWorkspaceEvent(state, sequenced("trade_batch", 3, {
      component: "trades", payload: { trades: [trade("later", 20), trade("earlier", 10), trade("later", 20)] },
    }), "BTCUSDT", "5");
    expect(trades.decision).toBe("APPLIED");
    expect(trades.state.snapshot.trades.map((item) => item.id)).toEqual(["later", "earlier"]);
    state = trades.state;

    const candles = applyWorkspaceEvent(state, sequenced("candle_update", 4, {
      component: "candles", payload: { interval: "5", candles: [
        { action: "replace", startTime: 1000, open: "1", high: "3", low: "1", close: "2" },
        { action: "append", startTime: 2000, open: "2", high: "2", low: "2", close: "2" },
      ] },
    }), "BTCUSDT", "5");
    expect(candles.decision).toBe("APPLIED");
    expect(candles.state.snapshot.candles.map((item) => item.close)).toEqual([2, 2]);
    expect(candles.state.authority).toMatchObject({ generation: 7, eventSequence: 4, state: "READY" });
  });

  it("fails closed on wrong book base and wrong candle source interval", () => {
    const ready = applyWorkspaceEvent(empty(), snapshot(), "BTCUSDT", "5").state;
    expect(applyWorkspaceEvent(ready, sequenced("book_delta", 2, {
      component: "book", payload: { base_version: 2, new_version: 4, bids: [], asks: [] },
    }), "BTCUSDT", "5").decision).toBe("RESNAPSHOT_REQUIRED");
    expect(applyWorkspaceEvent(ready, sequenced("candle_update", 2, {
      component: "candles", payload: { interval: "1", candles: [] },
    }), "BTCUSDT", "5").decision).toBe("RESNAPSHOT_REQUIRED");
  });
});

describe("M7 Workspace reconnect chaos", () => {
  it("coalesces disconnect bursts, rejects stale attachment events, and reconnects fresh after malformed input", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const store = new BackendWorkspaceMarketDataStore((url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    store.setSymbol("BTCUSDT");
    store.start();
    sockets[0].message(snapshot());
    sockets[0].disconnect();
    sockets[0].disconnect();
    vi.advanceTimersByTime(1000);
    expect(sockets).toHaveLength(2);
    expect(sockets[1].url).toContain("stream_id=stream-7");
    sockets[0].message(sequenced("health", 2));
    expect(store.getSnapshot().workspace?.eventSequence).toBe(1);
    sockets[1].malformed();
    expect(store.getSnapshot().workspace).toBeUndefined();
    expect(store.getSnapshot().book.health).toBe("DEGRADED");
    vi.advanceTimersByTime(1000);
    expect(sockets[2].url).not.toContain("stream_id=");
    store.dispose();
  });
});
