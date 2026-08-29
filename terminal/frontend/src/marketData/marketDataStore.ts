import type {
  Candle,
  MarketDataSnapshot,
  NormalizedOrderBook,
  PriceLevel,
  TradePrint,
} from "../contracts/marketData";
import { createDemoMarketData } from "./demoFeed";
import { marketApiRoutes } from "./apiRoutes";
import { projectSweepCenterRow } from "./domProjection";
import {
  BYBIT_INTERVAL_BY_TIMEFRAME,
  type ChartTimeframe,
} from "./timeframes";

export interface MarketDataPort {
  dispose(): void;
  getSnapshot(): MarketDataSnapshot;
  setTimeframe(timeframe: ChartTimeframe): void;
  setSymbol(symbol: string): void;
  start(): void;
  subscribe(listener: () => void): () => void;
}

type BackendTrade = {
  id: string;
  seq: number;
  symbol: string;
  side: "BUY" | "SELL";
  started_at_ms: number;
  ended_at_ms: number;
  trade_count: number;
  total_quantity: string;
  total_notional_usdt: string;
  first_execution_price: string;
  last_execution_price: string;
  sweep_low_price: string;
  sweep_high_price: string;
  swept_price_range: string;
  swept_ticks: number;
  tick_size: string;
  first_trade_seq: number;
  last_trade_seq: number;
  backend_first_received_at_ms: number;
  backend_last_received_at_ms: number;
  finalized_at_ms: number;
  book_correlation: null | {
    basis: "LATEST_BACKEND_KNOWN_AT_FINALIZATION";
    book_version: number;
    update_id: number;
    sequence: number;
    exchange_ts_ms: number;
    matching_engine_cts_ms: number | null;
    backend_received_at_ms: number;
    best_bid: string;
    best_ask: string;
  };
};

type BackendTradesEvent = {
  trades: BackendTrade[];
};

type BackendBookLevel = {
  price: string;
  size: string;
};

type BackendOrderBookEvent = {
  symbol: string;
  bids: BackendBookLevel[];
  asks: BackendBookLevel[];
  timestamp: number;
  receivedAt: number;
  matchingEngineCts: number | null;
  updateId: number;
  sequence: number;
  version: number;
  state: "CONNECTING" | "READY" | "DISCONNECTED" | "DEGRADED";
  source: "BYBIT_LINEAR_WS";
};

type BackendKline = {
  startTime: number;
  open: string;
  high: string;
  low: string;
  close: string;
};

type BackendKlinesEvent = {
  symbol: string;
  interval: string;
  candles: BackendKline[];
  tickSize: string;
  state: "CONNECTING" | "READY" | "DEGRADED";
};

const unavailableBook = (
  symbol: string,
  health: NormalizedOrderBook["health"],
): NormalizedOrderBook => ({
  symbol,
  bids: [],
  asks: [],
  health,
  receivedAt: "",
  availableDepth: 0,
});

export class BackendSseMarketDataStore implements MarketDataPort {
  private symbol = "ONGUSDT";
  private snapshot: MarketDataSnapshot = {
    ...createDemoMarketData(),
    candles: [],
    tickSize: null,
    book: unavailableBook("ONGUSDT", "NOT_READY"),
    trades: [],
  };

  private listeners = new Set<() => void>();
  private tradesSource: EventSource | null = null;
  private bookSource: EventSource | null = null;
  private klinesSource: EventSource | null = null;
  private tradesReconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private bookReconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private klinesReconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private timeframe: ChartTimeframe = "5m";
  private started = false;

  start = () => {
    if (this.started) return;
    this.started = true;
    this.connectTrades();
    this.connectOrderBook();
    this.connectKlines();
  };

  getSnapshot = () => this.snapshot;

  dispose = () => {
    this.started = false;
    this.tradesSource?.close();
    this.bookSource?.close();
    this.klinesSource?.close();
    this.tradesSource = null;
    this.bookSource = null;
    this.klinesSource = null;
    if (this.tradesReconnectTimer) clearTimeout(this.tradesReconnectTimer);
    if (this.bookReconnectTimer) clearTimeout(this.bookReconnectTimer);
    if (this.klinesReconnectTimer) clearTimeout(this.klinesReconnectTimer);
    this.tradesReconnectTimer = null;
    this.bookReconnectTimer = null;
    this.klinesReconnectTimer = null;
  };

  setTimeframe = (timeframe: ChartTimeframe) => {
    if (timeframe === this.timeframe) return;
    this.timeframe = timeframe;
    if (this.klinesReconnectTimer) {
      clearTimeout(this.klinesReconnectTimer);
      this.klinesReconnectTimer = null;
    }
    if (this.klinesSource) {
      this.klinesSource.close();
      this.klinesSource = null;
    }
    this.snapshot = { ...this.snapshot, candles: [] };
    this.emit();
    if (this.started) this.connectKlines();
  };

  setSymbol = (symbol: string) => {
    const normalized = symbol.trim().toUpperCase();
    if (!normalized || normalized === this.symbol) return;
    this.symbol = normalized;
    this.closeSources();
    this.snapshot = {
      ...this.snapshot,
      book: unavailableBook(normalized, "SYNCING"),
      candles: [],
      tickSize: null,
      trades: [],
      ownOrders: [],
    };
    this.emit();
    if (this.started) {
      this.connectTrades();
      this.connectOrderBook();
      this.connectKlines();
    }
  };

  private closeSources() {
    this.tradesSource?.close();
    this.bookSource?.close();
    this.klinesSource?.close();
    this.tradesSource = null;
    this.bookSource = null;
    this.klinesSource = null;
    if (this.tradesReconnectTimer) clearTimeout(this.tradesReconnectTimer);
    if (this.bookReconnectTimer) clearTimeout(this.bookReconnectTimer);
    if (this.klinesReconnectTimer) clearTimeout(this.klinesReconnectTimer);
    this.tradesReconnectTimer = null;
    this.bookReconnectTimer = null;
    this.klinesReconnectTimer = null;
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);

    return () => {
      this.listeners.delete(listener);
    };
  };

  private emit() {
    for (const listener of this.listeners) {
      listener();
    }
  }

  private connectTrades() {
    if (!this.started) return;
    if (this.tradesSource) {
      this.tradesSource.close();
    }

    const symbol = this.symbol;
    const source = new EventSource(marketApiRoutes.trades(symbol));

    this.tradesSource = source;

    source.onmessage = (event) => {
      if (this.tradesSource !== source || this.symbol !== symbol) return;
      const browserReceivedAtMs = Date.now();
      let payload: BackendTradesEvent;

      try {
        payload = JSON.parse(event.data) as BackendTradesEvent;
      } catch {
        return;
      }

      if (!Array.isArray(payload.trades) || payload.trades.length === 0) {
        return;
      }

      const incoming: TradePrint[] = payload.trades.flatMap((trade) => {
        if (trade.symbol !== symbol) return [];
        const totalQuantity = Number(trade.total_quantity);
        const totalNotionalUsdt = Number(trade.total_notional_usdt);
        const firstExecutionPrice = Number(trade.first_execution_price);
        const lastExecutionPrice = Number(trade.last_execution_price);
        const sweepLowPrice = Number(trade.sweep_low_price);
        const sweepHighPrice = Number(trade.sweep_high_price);
        const sweptPriceRange = Number(trade.swept_price_range);
        const tickSize = Number(trade.tick_size);

        if (
          !Number.isFinite(totalQuantity) ||
          totalQuantity <= 0 ||
          !Number.isFinite(totalNotionalUsdt) ||
          totalNotionalUsdt <= 0 ||
          !Number.isFinite(firstExecutionPrice) ||
          !Number.isFinite(lastExecutionPrice) ||
          !Number.isFinite(sweepLowPrice) ||
          !Number.isFinite(sweepHighPrice) ||
          sweepHighPrice < sweepLowPrice ||
          !Number.isFinite(sweptPriceRange) ||
          sweptPriceRange < 0 ||
          !Number.isFinite(tickSize) ||
          tickSize <= 0 ||
          !Number.isInteger(trade.trade_count) ||
          trade.trade_count <= 0 ||
          !Number.isInteger(trade.swept_ticks) ||
          trade.swept_ticks <= 0 ||
          (trade.side !== "BUY" && trade.side !== "SELL")
        ) {
          return [];
        }

        return [{
          id: trade.id,
          side: trade.side,
          startedAtMs: trade.started_at_ms,
          endedAtMs: trade.ended_at_ms,
          tradeCount: trade.trade_count,
          totalQuantity,
          totalNotionalUsdt,
          firstExecutionPrice,
          lastExecutionPrice,
          sweepLowPrice,
          sweepHighPrice,
          sweptPriceRange,
          sweptTicks: trade.swept_ticks,
          tickSize,
          rowOffset: projectSweepCenterRow(
            this.snapshot.book,
            sweepLowPrice,
            sweepHighPrice,
            tickSize,
          ),
          firstTradeSeq: trade.first_trade_seq,
          lastTradeSeq: trade.last_trade_seq,
          backendFirstReceivedAtMs: trade.backend_first_received_at_ms,
          backendLastReceivedAtMs: trade.backend_last_received_at_ms,
          finalizedAtMs: trade.finalized_at_ms,
          browserReceivedAtMs,
          bookCorrelation: trade.book_correlation === null ? null : {
            basis: trade.book_correlation.basis,
            bookVersion: trade.book_correlation.book_version,
            updateId: trade.book_correlation.update_id,
            sequence: trade.book_correlation.sequence,
            exchangeTimestampMs: trade.book_correlation.exchange_ts_ms,
            matchingEngineCtsMs: trade.book_correlation.matching_engine_cts_ms,
            backendReceivedAtMs: trade.book_correlation.backend_received_at_ms,
            bestBid: Number(trade.book_correlation.best_bid),
            bestAsk: Number(trade.book_correlation.best_ask),
          },
          correlatedBookExchangeSkewMs: trade.book_correlation === null
            ? null
            : trade.book_correlation.exchange_ts_ms - trade.ended_at_ms,
          correlatedBookCtsSkewMs:
            trade.book_correlation?.matching_engine_cts_ms == null
              ? null
              : trade.book_correlation.matching_engine_cts_ms - trade.ended_at_ms,
        }];
      });

      if (incoming.length === 0) {
        return;
      }

      this.snapshot = {
        ...this.snapshot,
        trades: [
          ...this.snapshot.trades,
          ...incoming,
        ].slice(-80),
        source: "LIVE_NORMALIZED",
      };

      this.emit();
    };

    source.onerror = () => {
      source.close();

      if (this.tradesSource === source) {
        this.tradesSource = null;
      }

      if (this.tradesReconnectTimer) {
        clearTimeout(this.tradesReconnectTimer);
      }

      this.tradesReconnectTimer = setTimeout(() => {
        this.tradesReconnectTimer = null;
        if (this.started && this.symbol === symbol) this.connectTrades();
      }, 1000);
    };
  }

  private connectOrderBook() {
    if (!this.started) return;
    if (this.bookSource) {
      this.bookSource.close();
    }

    const symbol = this.symbol;
    const source = new EventSource(marketApiRoutes.book(symbol));

    this.bookSource = source;

    source.onmessage = (event) => {
      if (this.bookSource !== source || this.symbol !== symbol) return;
      const browserReceivedAtMs = Date.now();
      let payload: BackendOrderBookEvent;

      try {
        payload = JSON.parse(event.data) as BackendOrderBookEvent;
      } catch {
        return;
      }

      if (payload.symbol !== symbol || payload.state !== "READY") {
        const health = payload.state === "CONNECTING" ? "SYNCING" : "DEGRADED";
        this.setBookUnavailable(health);
        return;
      }

      const bids = this.normalizeLevels(payload.bids, true);
      const asks = this.normalizeLevels(payload.asks, false);
      if (bids.length === 0 || asks.length === 0) {
        this.setBookUnavailable("DEGRADED");
        return;
      }

      this.snapshot = {
        ...this.snapshot,
        book: {
          symbol: payload.symbol,
          bids,
          asks,
          health: "READY",
          receivedAt: new Date(payload.receivedAt).toISOString(),
          availableDepth: Math.min(bids.length, asks.length),
          exchangeTimestampMs: payload.timestamp,
          matchingEngineCtsMs: payload.matchingEngineCts,
          backendReceivedAtMs: payload.receivedAt,
          updateId: payload.updateId,
          sequence: payload.sequence,
          bookVersion: payload.version,
          browserReceivedAtMs,
        },
        source: "LIVE_NORMALIZED",
      };
      this.emit();
    };

    source.onerror = () => {
      source.close();
      if (this.bookSource !== source || this.symbol !== symbol) return;
      this.bookSource = null;

      this.setBookUnavailable("DEGRADED");

      if (this.bookReconnectTimer) {
        clearTimeout(this.bookReconnectTimer);
      }

      this.bookReconnectTimer = setTimeout(() => {
        this.bookReconnectTimer = null;
        if (this.started && this.symbol === symbol) this.connectOrderBook();
      }, 1000);
    };
  }

  private connectKlines() {
    if (!this.started) return;
    if (this.klinesSource) {
      this.klinesSource.close();
    }
    const timeframe = this.timeframe;
    const symbol = this.symbol;
    const interval = BYBIT_INTERVAL_BY_TIMEFRAME[timeframe];
    const source = new EventSource(
      marketApiRoutes.candles(symbol, interval),
    );
    this.klinesSource = source;

    source.onmessage = (event) => {
      if (this.klinesSource !== source || this.timeframe !== timeframe || this.symbol !== symbol) return;
      let payload: BackendKlinesEvent;
      try {
        payload = JSON.parse(event.data) as BackendKlinesEvent;
      } catch {
        return;
      }
      if (
        payload.symbol !== symbol
        || payload.interval !== interval
        || payload.state !== "READY"
        || !Array.isArray(payload.candles)
      ) {
        return;
      }

      const candles = payload.candles.flatMap<Candle>((candle) => {
        const open = Number(candle.open);
        const high = Number(candle.high);
        const low = Number(candle.low);
        const close = Number(candle.close);
        if (
          !Number.isInteger(candle.startTime)
          || candle.startTime <= 0
          || !Number.isFinite(open)
          || !Number.isFinite(high)
          || !Number.isFinite(low)
          || !Number.isFinite(close)
          || open <= 0
          || high < Math.max(open, close)
          || low <= 0
          || low > Math.min(open, close)
        ) {
          return [];
        }
        return [{
          time: new Date(candle.startTime).toISOString(),
          open,
          high,
          low,
          close,
        }];
      });
      const tickSize = Number(payload.tickSize);
      if (
        candles.length === 0
        || candles.length !== payload.candles.length
        || !Number.isFinite(tickSize)
        || tickSize <= 0
        || candles.some((candle, index) => (
          index > 0
          && Date.parse(candle.time) <= Date.parse(candles[index - 1].time)
        ))
      ) {
        return;
      }

      this.snapshot = {
        ...this.snapshot,
        candles,
        tickSize,
        source: "LIVE_NORMALIZED",
      };
      this.emit();
    };

    source.onerror = () => {
      source.close();
      if (this.klinesSource !== source || this.timeframe !== timeframe) return;
      this.klinesSource = null;
      if (this.klinesReconnectTimer) {
        clearTimeout(this.klinesReconnectTimer);
      }
      this.klinesReconnectTimer = setTimeout(() => {
        this.klinesReconnectTimer = null;
        if (this.started && this.timeframe === timeframe && this.symbol === symbol) this.connectKlines();
      }, 1000);
    };
  }

  private normalizeLevels(
    levels: BackendBookLevel[],
    descending: boolean,
  ): PriceLevel[] {
    if (!Array.isArray(levels)) {
      return [];
    }

    return levels
      .flatMap((level) => {
        const price = Number(level.price);
        const quantity = Number(level.size);
        if (
          !Number.isFinite(price) ||
          price <= 0 ||
          !Number.isFinite(quantity) ||
          quantity <= 0
        ) {
          return [];
        }
        return [{ price, quantity }];
      })
      .sort((left, right) =>
        descending ? right.price - left.price : left.price - right.price,
      );
  }

  private setBookUnavailable(health: NormalizedOrderBook["health"]) {
    this.snapshot = {
      ...this.snapshot,
      book: unavailableBook(this.symbol, health),
    };
    this.emit();
  }
}

export const marketDataStore: MarketDataPort =
  new BackendSseMarketDataStore();

if (import.meta.hot) {
  import.meta.hot.dispose(() => marketDataStore.dispose());
  import.meta.hot.accept();
}
