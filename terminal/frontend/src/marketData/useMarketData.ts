import { useSyncExternalStore } from "react";
import { marketDataStore } from "./marketDataStore";
export function useMarketData() {
  return useSyncExternalStore(
    marketDataStore.subscribe,
    marketDataStore.getSnapshot,
  );
}

export const setMarketTimeframe = marketDataStore.setTimeframe;
