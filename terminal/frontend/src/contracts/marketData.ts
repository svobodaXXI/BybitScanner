export type BookHealth =
  | "NOT_READY"
  | "SYNCING"
  | "READY"
  | "STALE"
  | "DEGRADED";
export type MarketSide = "BUY" | "SELL";

export interface PriceLevel {
  price: number;
  quantity: number;
}
export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}
export interface TradePrint {
  id: string;
  side: MarketSide;
  startedAtMs: number;
  endedAtMs: number;
  tradeCount: number;
  totalQuantity: number;
  totalNotionalUsdt: number;
  firstExecutionPrice: number;
  lastExecutionPrice: number;
  sweepLowPrice: number;
  sweepHighPrice: number;
  sweptPriceRange: number;
  sweptTicks: number;
  tickSize: number;
  rowOffset: number | null;
  firstTradeSeq: number;
  lastTradeSeq: number;
  backendFirstReceivedAtMs: number;
  backendLastReceivedAtMs: number;
  finalizedAtMs: number;
  browserReceivedAtMs: number;
  bookCorrelation: BookCorrelation | null;
  correlatedBookExchangeSkewMs: number | null;
  correlatedBookCtsSkewMs: number | null;
}
export interface BookCorrelation {
  basis: "LATEST_BACKEND_KNOWN_AT_FINALIZATION";
  bookVersion: number;
  updateId: number;
  sequence: number;
  exchangeTimestampMs: number;
  matchingEngineCtsMs: number | null;
  backendReceivedAtMs: number;
  bestBid: number;
  bestAsk: number;
}
export interface OwnOrder {
  id: string;
  price: number;
  notionalUsdt: number;
  side: MarketSide;
}

export interface NormalizedOrderBook {
  symbol: string;
  bids: readonly PriceLevel[];
  asks: readonly PriceLevel[];
  health: BookHealth;
  receivedAt: string;
  availableDepth: number;
  exchangeTimestampMs?: number;
  matchingEngineCtsMs?: number | null;
  backendReceivedAtMs?: number;
  updateId?: number;
  sequence?: number;
  bookVersion?: number;
  browserReceivedAtMs?: number;
}

/**
 * Frontend-facing normalized data only. Raw exchange snapshot/delta fields and
 * sequence mechanics belong to the future Market Data Engine and its adapters.
 */
export interface MarketDataSnapshot {
  book: NormalizedOrderBook;
  candles: readonly Candle[];
  trades: readonly TradePrint[];
  ownOrders: readonly OwnOrder[];
  source: "DEVELOPMENT" | "LIVE_NORMALIZED";
}
