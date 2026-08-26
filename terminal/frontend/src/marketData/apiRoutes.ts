export const marketApiRoutes = {
  book: (symbol: string) => `/api/public-orderbook/stream?symbol=${encodeURIComponent(symbol)}`,
  candles: (symbol: string, interval: string) =>
    `/api/public-klines/stream?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}`,
  paperState: (symbol: string) => `/api/paper-state?symbol=${encodeURIComponent(symbol)}`,
  trades: (symbol: string) => `/api/public-trades/stream?symbol=${encodeURIComponent(symbol)}`,
};
