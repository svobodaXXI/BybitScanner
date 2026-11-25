import { afterEach, describe, expect, it, vi } from "vitest";
import { BackendWorkspaceMarketDataStore, FIRST_SNAPSHOT_DEADLINE_MS } from "./workspaceMarketDataStore";

class FakeSocket {
  onopen: (() => void) | null = null;
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

  it("allows only one fast reconnect before the new symbol's first snapshot", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const store = new BackendWorkspaceMarketDataStore((url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    store.start();
    sockets[0].message(snapshotEvent());
    store.setSymbol("BTCUSDT", 8);
    sockets[1].disconnect();
    vi.advanceTimersByTime(249);
    expect(sockets).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(3);
    expect(sockets[2].url).toContain("symbol=BTCUSDT");
    expect(sockets[2].url).not.toContain("stream_id=");
    expect(store.getSnapshot().book.symbol).toBe("ONGUSDT");
    sockets[2].disconnect();
    vi.advanceTimersByTime(999);
    expect(sockets).toHaveLength(3);
    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(4);
    sockets[3].message({
      ...snapshotEvent(), symbol: "BTCUSDT", workspace_generation: 8,
      stream_id: "stream-btc",
    });
    expect(store.getSnapshot().book.symbol).toBe("BTCUSDT");
    sockets[3].disconnect();
    vi.advanceTimersByTime(999);
    expect(sockets).toHaveLength(4);
    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(5);
    expect(sockets[4].url).toContain("stream_id=stream-btc");
    store.dispose();
  });

  it("recovers once from a silent new socket without accepting a stale snapshot", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const store = new BackendWorkspaceMarketDataStore((url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    store.start();
    sockets[0].message(snapshotEvent());
    store.setSymbol("BTCUSDT", 8);
    sockets[1].onopen?.();
    vi.advanceTimersByTime(FIRST_SNAPSHOT_DEADLINE_MS - 1);
    expect(sockets).toHaveLength(2);
    expect(store.getSnapshot().book.symbol).toBe("ONGUSDT");
    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(3);
    expect(sockets[1].closed).toBe(true);
    expect(store.getSnapshot().book.health).toBe("STALE");
    const candidate = { ...snapshotEvent(), symbol: "BTCUSDT", workspace_generation: 8, stream_id: "new" };
    sockets[1].message(candidate);
    sockets[1].disconnect();
    expect(store.getSnapshot().book.symbol).toBe("ONGUSDT");
    // The replacement is bounded; no timeout-induced reconnect storm.
    vi.advanceTimersByTime(FIRST_SNAPSHOT_DEADLINE_MS * 5);
    expect(sockets).toHaveLength(3);
    sockets[2].onopen?.();
    sockets[2].message({ ...candidate, workspace_generation: 7 });
    expect(store.getSnapshot().book.symbol).toBe("ONGUSDT");
    sockets[2].message(candidate);
    expect(store.getSnapshot().workspace).toMatchObject({ generation: 8, symbol: "BTCUSDT" });
    expect(store.getNavigationTransportTiming()).toBe("WS 2 попыток / 2 открытий / 0 закрытий / 1 отклонений / 1 тайм-аутов");
    vi.advanceTimersByTime(FIRST_SNAPSHOT_DEADLINE_MS * 5);
    expect(sockets).toHaveLength(3);
    store.dispose();
  });

  it("cancels first-snapshot deadline on accepted snapshot, timeframe change and dispose", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const store = new BackendWorkspaceMarketDataStore((url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    store.start();
    sockets[0].message(snapshotEvent());
    store.setSymbol("BTCUSDT", 8);
    sockets[1].message({ ...snapshotEvent(), symbol: "BTCUSDT", workspace_generation: 8, stream_id: "btc" });
    vi.advanceTimersByTime(FIRST_SNAPSHOT_DEADLINE_MS * 2);
    expect(sockets).toHaveLength(2);
    store.setSymbol("ETHUSDT", 9);
    store.setTimeframe("1m");
    vi.advanceTimersByTime(FIRST_SNAPSHOT_DEADLINE_MS * 2);
    expect(sockets).toHaveLength(4);
    store.setSymbol("APRUSDT", 10);
    store.dispose();
    vi.advanceTimersByTime(FIRST_SNAPSHOT_DEADLINE_MS * 2);
    expect(sockets).toHaveLength(5);
  });

  it("cannot promote a candidate snapshot with a generation other than its ACK", () => {
    const sockets: FakeSocket[] = [];
    const store = new BackendWorkspaceMarketDataStore((url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    store.start();
    sockets[0].message(snapshotEvent());
    store.setSymbol("BTCUSDT", 8);
    const candidate = {
      ...snapshotEvent(), symbol: "BTCUSDT", stream_id: "stream-btc",
      book: { ...snapshotEvent().book },
    };
    sockets[1].message({ ...candidate, workspace_generation: 7 });
    expect(store.getSnapshot().book.symbol).toBe("ONGUSDT");
    expect(store.getSnapshot().workspace?.generation).toBe(4);
    sockets[1].message({ ...candidate, workspace_generation: 8 });
    expect(store.getSnapshot().book.symbol).toBe("BTCUSDT");
    expect(store.getSnapshot().workspace?.generation).toBe(8);
    store.dispose();
  });

  it("switches 5m to 1m and back only through complete atomic snapshots", () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const store = new BackendWorkspaceMarketDataStore((url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });
    store.start();
    sockets[0].message(snapshotEvent());
    expect(store.getSnapshot().workspace).toMatchObject({
      interval: "5", generation: 4, eventSequence: 1, state: "READY",
    });
    expect(store.getSnapshot().book.health).toBe("READY");
    expect(store.getSnapshot().candles).toHaveLength(1);

    store.setTimeframe("1m");
    expect(sockets).toHaveLength(2);
    expect(sockets[0].closed).toBe(true);
    expect(sockets[1].url).toContain("interval=1");
    expect(sockets[1].url).not.toContain("stream_id=");
    expect(store.getSnapshot().workspace?.interval).toBe("5");
    sockets[0].message({
      stream_id: "stream-1", event_sequence: 2, symbol: "ONGUSDT",
      workspace_generation: 4, kind: "health", state: "DEGRADED",
      component: "book", payload: {},
    });
    expect(store.getSnapshot().book.health).toBe("READY");

    sockets[1].message({
      ...snapshotEvent(), stream_id: "stream-2", event_sequence: 1,
      candles: { ...snapshotEvent().candles, interval: "1" },
    });
    expect(store.getSnapshot().workspace).toMatchObject({
      streamId: "stream-2", interval: "1", generation: 4,
      eventSequence: 1, state: "READY",
    });
    expect(store.getSnapshot().book.health).toBe("READY");
    expect(store.getSnapshot().candles).toHaveLength(1);

    store.setTimeframe("5m");
    expect(sockets).toHaveLength(3);
    expect(sockets[1].closed).toBe(true);
    expect(sockets[2].url).toContain("interval=5");
    expect(sockets[2].url).not.toContain("stream_id=");
    sockets[2].message({ ...snapshotEvent(), stream_id: "stream-3" });
    expect(store.getSnapshot().workspace).toMatchObject({
      streamId: "stream-3", interval: "5", generation: 4,
      eventSequence: 1, state: "READY",
    });
    vi.runOnlyPendingTimers();
    expect(sockets).toHaveLength(3);
    store.dispose();
  });
});
