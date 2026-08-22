export type BookHealth =
  | "NOT_READY"
  | "SYNCING"
  | "READY"
  | "STALE"
  | "DEGRADED";

export interface PriceLevel {
  price: string;
  quantity: string;
}

export interface NormalizedOrderBook {
  symbol: string;
  bids: readonly PriceLevel[];
  asks: readonly PriceLevel[];
  health: BookHealth;
  receivedAt: string;
}

/**
 * Frontend-facing normalized data only. Raw exchange snapshot/delta fields and
 * sequence mechanics belong to the future Market Data Engine and its adapters.
 */
export interface MarketDataSnapshot {
  book: NormalizedOrderBook;
}
