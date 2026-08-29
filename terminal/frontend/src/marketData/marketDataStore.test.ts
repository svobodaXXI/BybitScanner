import { afterEach, describe, expect, it, vi } from "vitest";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  close() { this.closed = true; }

  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.resetModules();
  FakeEventSource.instances = [];
});

describe("live market-data temporal metadata", () => {
  it("clears symbol-scoped projections and rejects late events from the previous symbol", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { BackendSseMarketDataStore } = await import("./marketDataStore");
    const store = new BackendSseMarketDataStore();
    store.start();
    const oldSources = FakeEventSource.instances.slice(-3);

    store.setSymbol("BTCUSDT");
    expect(store.getSnapshot()).toMatchObject({
      book: { symbol: "BTCUSDT", health: "SYNCING", bids: [], asks: [] },
      candles: [], trades: [], tickSize: null,
    });
    oldSources.find((source) => source.url.includes("public-orderbook"))?.emit({
      symbol: "ONGUSDT", bids: [{ price: "1", size: "2" }],
      asks: [{ price: "2", size: "3" }], timestamp: 1, receivedAt: 1,
      matchingEngineCts: null, updateId: 1, sequence: 1, version: 1,
      state: "READY", source: "BYBIT_LINEAR_WS",
    });
    expect(store.getSnapshot().book).toMatchObject({ symbol: "BTCUSDT", health: "SYNCING", bids: [] });

    const newBook = FakeEventSource.instances.slice(-3)
      .find((source) => source.url.includes("public-orderbook"))!;
    expect(newBook.url).toContain("symbol=BTCUSDT");
    newBook.emit({
      symbol: "BTCUSDT", bids: [{ price: "10", size: "2" }],
      asks: [{ price: "11", size: "3" }], timestamp: 2, receivedAt: 2,
      matchingEngineCts: null, updateId: 2, sequence: 2, version: 2,
      state: "READY", source: "BYBIT_LINEAR_WS",
    });
    expect(store.getSnapshot().book).toMatchObject({ symbol: "BTCUSDT", health: "READY" });
    oldSources.find((source) => source.url.includes("public-orderbook"))?.onerror?.();
    expect(store.getSnapshot().book).toMatchObject({ symbol: "BTCUSDT", health: "READY" });
  });
  it("preserves backend fields and records browser arrival for both SSE streams", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.spyOn(Date, "now").mockReturnValueOnce(5000).mockReturnValueOnce(6000);
    const { BackendSseMarketDataStore } = await import("./marketDataStore");
    const store = new BackendSseMarketDataStore();
    store.start();
    const sources = FakeEventSource.instances.slice(-3);
    const trades = sources.find((source) => source.url.includes("public-trades"));
    const book = sources.find((source) => source.url.includes("public-orderbook"));

    book?.emit({
      symbol: "ONGUSDT",
      bids: [{ price: "1", size: "2" }],
      asks: [{ price: "2", size: "3" }],
      timestamp: 4900,
      matchingEngineCts: 4899,
      receivedAt: 4950,
      updateId: 10,
      sequence: 20,
      version: 3,
      state: "READY",
      source: "BYBIT_LINEAR_WS",
    });
    trades?.emit({
      trades: [{
        id: "trade-1", seq: 30, symbol: "ONGUSDT", side: "BUY",
        started_at_ms: 4980, ended_at_ms: 4990, trade_count: 2,
        total_quantity: "4", total_notional_usdt: "6",
        first_execution_price: "1.4", last_execution_price: "1.5",
        sweep_low_price: "1.4", sweep_high_price: "1.5",
        swept_price_range: "0.1", swept_ticks: 2, tick_size: "0.1",
        first_trade_seq: 29, last_trade_seq: 30,
        backend_first_received_at_ms: 5010,
        backend_last_received_at_ms: 5020,
        finalized_at_ms: 5050,
        book_correlation: {
          basis: "LATEST_BACKEND_KNOWN_AT_FINALIZATION",
          book_version: 3, update_id: 10, sequence: 20,
          exchange_ts_ms: 4900, matching_engine_cts_ms: 4899,
          backend_received_at_ms: 4950, best_bid: "1", best_ask: "2",
        },
      }],
    });

    const snapshot = store.getSnapshot();
    expect(snapshot.book).toMatchObject({
      receivedAt: new Date(4950).toISOString(),
      exchangeTimestampMs: 4900,
      matchingEngineCtsMs: 4899,
      backendReceivedAtMs: 4950,
      updateId: 10,
      sequence: 20,
      bookVersion: 3,
      browserReceivedAtMs: 5000,
    });
    expect(snapshot.trades[0]).toMatchObject({
      firstTradeSeq: 29,
      lastTradeSeq: 30,
      finalizedAtMs: 5050,
      browserReceivedAtMs: 6000,
      correlatedBookExchangeSkewMs: -90,
      correlatedBookCtsSkewMs: -91,
      bookCorrelation: {
        basis: "LATEST_BACKEND_KNOWN_AT_FINALIZATION",
        bookVersion: 3,
        updateId: 10,
        sequence: 20,
      },
    });
  });

  it("starts without demo candles and replaces live 5m snapshots", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { BackendSseMarketDataStore } = await import("./marketDataStore");
    const store = new BackendSseMarketDataStore();
    store.start();
    const source = FakeEventSource.instances
      .slice(-3)
      .find((item) => item.url.includes("public-klines"));

    expect(store.getSnapshot().candles).toEqual([]);
    expect(source?.url).toBe(
      "/api/public-klines/stream?symbol=ONGUSDT&interval=5",
    );
    source?.emit({
      symbol: "ONGUSDT",
      interval: "5",
      state: "READY",
      tickSize: "0.00001",
      candles: [
        { startTime: 300000, open: "1", high: "1.2", low: "0.9", close: "1.1" },
        { startTime: 600000, open: "1.1", high: "1.3", low: "1", close: "1.2" },
      ],
    });
    expect(store.getSnapshot().candles).toEqual([
      { time: new Date(300000).toISOString(), open: 1, high: 1.2, low: 0.9, close: 1.1 },
      { time: new Date(600000).toISOString(), open: 1.1, high: 1.3, low: 1, close: 1.2 },
    ]);
    expect(store.getSnapshot().tickSize).toBe(0.00001);

    source?.emit({
      symbol: "ONGUSDT",
      interval: "5",
      state: "READY",
      tickSize: "0.00001",
      candles: [
        { startTime: 300000, open: "1", high: "1.2", low: "0.9", close: "1.1" },
        { startTime: 600000, open: "1.1", high: "1.35", low: "1", close: "1.25" },
        { startTime: 900000, open: "1.25", high: "1.4", low: "1.2", close: "1.35" },
      ],
    });
    expect(store.getSnapshot().candles).toHaveLength(3);
    expect(store.getSnapshot().candles.at(-2)?.close).toBe(1.25);
    expect(store.getSnapshot().candles.at(-1)?.time).toBe(
      new Date(900000).toISOString(),
    );
  });

  it("closes the previous candle stream and maps each supported timeframe", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { BackendSseMarketDataStore } = await import("./marketDataStore");
    const store = new BackendSseMarketDataStore();
    store.start();
    const expected = [
      ["15s", "15s"], ["1m", "1"], ["5m", "5"],
      ["15m", "15"], ["1h", "60"], ["1d", "D"],
    ] as const;
    let previous = FakeEventSource.instances.at(-1)!;
    for (const [timeframe, interval] of expected) {
      store.setTimeframe(timeframe);
      const current = FakeEventSource.instances.at(-1)!;
      if (current !== previous) expect(previous.closed).toBe(true);
      expect(current.url).toBe(
        `/api/public-klines/stream?symbol=ONGUSDT&interval=${interval}`,
      );
      current.emit({
        symbol: "ONGUSDT", interval, state: "READY", tickSize: "0.00001",
        candles: [
          { startTime: 300000, open: "1", high: "2", low: "0.5", close: "1.5" },
        ],
      });
      expect(store.getSnapshot().candles).toHaveLength(1);
      previous = current;
    }
  });

  it("switches only candles while book and trades remain live", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { BackendSseMarketDataStore } = await import("./marketDataStore");
    const store = new BackendSseMarketDataStore();
    store.start();
    const sources = FakeEventSource.instances.slice(-3);
    const trades = sources.find((source) => source.url.includes("public-trades"))!;
    const book = sources.find((source) => source.url.includes("public-orderbook"))!;
    const oldCandles = sources.find((source) => source.url.includes("public-klines"))!;

    book.emit({
      symbol: "ONGUSDT", bids: [{ price: "1", size: "2" }],
      asks: [{ price: "2", size: "3" }], timestamp: 1000,
      matchingEngineCts: 999, receivedAt: 1001, updateId: 1,
      sequence: 2, version: 1, state: "READY", source: "BYBIT_LINEAR_WS",
    });
    trades.emit({ trades: [{
      id: "trade-live", seq: 1, symbol: "ONGUSDT", side: "BUY",
      started_at_ms: 1000, ended_at_ms: 1000, trade_count: 1,
      total_quantity: "1", total_notional_usdt: "1.5",
      first_execution_price: "1.5", last_execution_price: "1.5",
      sweep_low_price: "1.5", sweep_high_price: "1.5",
      swept_price_range: "0", swept_ticks: 1, tick_size: "0.1",
      first_trade_seq: 1, last_trade_seq: 1,
      backend_first_received_at_ms: 1001,
      backend_last_received_at_ms: 1001, finalized_at_ms: 1002,
      book_correlation: null,
    }] });

    store.setTimeframe("15m");
    const nextCandles = FakeEventSource.instances.at(-1)!;
    expect(oldCandles.closed).toBe(true);
    expect(book.closed).toBe(false);
    expect(trades.closed).toBe(false);
    expect(store.getSnapshot().book.health).toBe("READY");
    expect(store.getSnapshot().trades).toHaveLength(1);
    expect(store.getSnapshot().candles).toEqual([]);

    nextCandles.emit({
      symbol: "ONGUSDT", interval: "15", state: "READY",
      tickSize: "0.00001", candles: [
        { startTime: 900000, open: "1", high: "2", low: "0.5", close: "1.5" },
      ],
    });
    expect(store.getSnapshot().candles).toHaveLength(1);
    expect(store.getSnapshot().book.health).toBe("READY");
    expect(store.getSnapshot().trades[0]?.id).toBe("trade-live");
  });

  it("disposes every stream so hot reload cannot leave orphan subscriptions", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const { BackendSseMarketDataStore } = await import("./marketDataStore");
    const store = new BackendSseMarketDataStore();
    store.start();
    const sources = FakeEventSource.instances.slice(-3);
    store.dispose();
    expect(sources.every((source) => source.closed)).toBe(true);
  });
});
