import type { MarketDataSnapshot } from "../contracts/marketData";
import { createDemoMarketData } from "./demoFeed";
export interface MarketDataPort {
  getSnapshot(): MarketDataSnapshot;
  subscribe(listener: () => void): () => void;
}
class DevelopmentMarketDataStore implements MarketDataPort {
  private snapshot = createDemoMarketData();
  getSnapshot = () => this.snapshot;
  subscribe = () => () => undefined;
}
export const marketDataStore: MarketDataPort = new DevelopmentMarketDataStore();
