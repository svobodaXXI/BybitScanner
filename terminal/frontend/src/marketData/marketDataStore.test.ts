import { afterEach, describe, expect, it, vi } from "vitest";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  close() {}

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
  it("preserves backend fields and records browser arrival for both SSE streams", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.spyOn(Date, "now").mockReturnValueOnce(5000).mockReturnValueOnce(6000);
    const { BackendSseMarketDataStore } = await import("./marketDataStore");
    const store = new BackendSseMarketDataStore();
    const sources = FakeEventSource.instances.slice(-2);
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
});
