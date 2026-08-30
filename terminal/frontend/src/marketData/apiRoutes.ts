export const marketApiRoutes = {
  instruments: "/api/instruments",
  book: (symbol: string) => `/api/public-orderbook/stream?symbol=${encodeURIComponent(symbol)}`,
  candles: (symbol: string, interval: string) =>
    `/api/public-klines/stream?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}`,
  paperState: (symbol: string) => `/api/paper-state?symbol=${encodeURIComponent(symbol)}`,
  openPositions: "/api/open-positions",
  trades: (symbol: string) => `/api/public-trades/stream?symbol=${encodeURIComponent(symbol)}`,
  workspaceSymbol: "/api/workspace/symbol",
};
