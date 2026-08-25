import type {
  Candle,
  MarketDataSnapshot,
  PriceLevel,
  TradePrint,
} from "../contracts/marketData";

const mid = 64250;
const level = (price: number, index: number): PriceLevel => ({
  price,
  quantity: 0.8 + ((index * 17) % 19) / 5,
});
const candles: Candle[] = Array.from({ length: 24 }, (_, index) => {
  const open = mid - 180 + index * 14 + Math.sin(index * 1.4) * 42;
  const close = open + Math.sin(index * 2.1) * 55;
  return {
    time: `candle-${index}`,
    open,
    close,
    high: Math.max(open, close) + 28 + (index % 3) * 8,
    low: Math.min(open, close) - 24 - (index % 4) * 6,
  };
});
const trades: TradePrint[] = Array.from({ length: 18 }, (_, index) => ({
  id: `trade-${index}`,
  side: index % 3 === 0 ? "SELL" : "BUY",
  startedAtMs: index * 50,
  endedAtMs: index * 50,
  tradeCount: 1,
  totalQuantity: 0.012 + ((index * 13) % 45) / 100,
  totalNotionalUsdt: 100 + index * 20,
  firstExecutionPrice: mid,
  lastExecutionPrice: mid,
  sweepLowPrice: mid,
  sweepHighPrice: mid,
  sweptPriceRange: 0,
  sweptTicks: 1,
  tickSize: 0.5,
  rowOffset: 0,
}));
export function createDemoMarketData(): MarketDataSnapshot {
  return {
    source: "DEVELOPMENT",
    book: {
      symbol: "BTCUSDT",
      bids: Array.from({ length: 50 }, (_, index) =>
        level(mid - 0.5 - index * 0.5, index),
      ),
      asks: Array.from({ length: 50 }, (_, index) =>
        level(mid + 0.5 + index * 0.5, index + 4),
      ),
      health: "READY",
      receivedAt: "development-fixture",
      availableDepth: 50,
    },
    candles,
    trades,
    ownOrders: [
      { id: "paper-buy-100", price: mid - 1, notionalUsdt: 100, side: "BUY" },
      { id: "paper-buy-150", price: mid - 1, notionalUsdt: 150, side: "BUY" },
      { id: "paper-buy-250", price: mid - 1, notionalUsdt: 250, side: "BUY" },
      {
        id: "paper-sell-120",
        price: mid + 1.5,
        notionalUsdt: 120,
        side: "SELL",
      },
    ],
  };
}
