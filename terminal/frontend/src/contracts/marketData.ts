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
  time: string;
  price: number;
  quantity: number;
  side: MarketSide;
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
