import { useEffect, useSyncExternalStore } from "react";
import { marketDataStore } from "./marketDataStore";

export function useMarketData() {
  useEffect(() => {
    marketDataStore.start();

    return () => {
      marketDataStore.dispose();
    };
  }, []);

  return useSyncExternalStore(
    marketDataStore.subscribe,
    marketDataStore.getSnapshot,
  );
}

export const setMarketTimeframe = marketDataStore.setTimeframe;
export const setMarketSymbol = marketDataStore.setSymbol;
