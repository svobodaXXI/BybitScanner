import { afterEach, describe, expect, it, vi } from "vitest";
import { BackendWorkspaceMarketDataStore } from "./workspaceMarketDataStore";

class FakeSocket {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;
  constructor(readonly url: string) {}
  close() { this.closed = true; }
  message(payload: unknown) { this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent); }
  disconnect() { this.onclose?.(); }
}

const snapshotEvent = () => ({
  stream_id: "stream-1", event_sequence: 1, event_timestamp: 1000,
  symbol: "ONGUSDT", workspace_generation: 4, kind: "workspace_snapshot", state: "READY",
  instrument: { symbol: "ONGUSDT", tick_size: "0.0001", quantity_step: "1" },
  book: {
    kind: "book_snapshot", state: "READY", projection_version: 2,
    source_timestamp: 1000, upstream_update_id: 5, upstream_sequence: 6,
    bids: [{ price: "0.1", size: "2" }], asks: [{ price: "0.2", size: "3" }],
  },
  trades: { kind: "trade_bootstrap", state: "READY", projection_version: 1, trades: [] },
  candles: {
    kind: "candle_bootstrap", state: "READY", interval: "5", projection_version: 1,
    candles: [{ startTime: 1000, open: "1", high: "1", low: "1", close: "1" }],
  },
});

afterEach(() => vi.useRealTimers());

describe("multiplexed Workspace market-data store", () => {
  it("resumes after disconnect and reconnects fresh on a sequence gap", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const store = new BackendWorkspaceMarketDataStore((url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    store.start();
    expect(sockets[0].url).toContain("/api/workspace/stream?symbol=ONGUSDT&interval=5");
    sockets[0].message(snapshotEvent());
    expect(store.getSnapshot().workspace?.eventSequence).toBe(1);

    sockets[0].disconnect();
    expect(store.getSnapshot().book.health).toBe("STALE");
    vi.advanceTimersByTime(1000);
    expect(sockets[1].url).toContain("stream_id=stream-1");
    expect(sockets[1].url).toContain("after_sequence=1");

    sockets[1].message({
      stream_id: "stream-1", event_sequence: 3, symbol: "ONGUSDT",
      workspace_generation: 4, kind: "health", state: "READY", component: "stream", payload: {},
    });
    expect(sockets[1].closed).toBe(true);
    expect(store.getSnapshot().workspace).toBeUndefined();
    expect(store.getSnapshot().book.health).toBe("DEGRADED");
    vi.advanceTimersByTime(1000);
    expect(sockets[2].url).not.toContain("stream_id=");
    store.dispose();
  });

  it("keeps the old atomic view until a new symbol snapshot arrives", () => {
    const sockets: FakeSocket[] = [];
    const store = new BackendWorkspaceMarketDataStore((url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    store.start();
    sockets[0].message(snapshotEvent());
    store.setSymbol("BTCUSDT");
    expect(store.getSnapshot().book.symbol).toBe("ONGUSDT");
    expect(sockets[1].url).toContain("symbol=BTCUSDT");
    expect(sockets[1].url).not.toContain("stream_id=");
    store.dispose();
  });
});
