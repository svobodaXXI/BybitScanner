import { useEffect, useSyncExternalStore } from "react";
import { marketDataStore } from "./marketDataStore";

export function useMarketData() {
  useEffect(() => {
    const startTimer = globalThis.setTimeout(() => {
      marketDataStore.start();
    }, 1000);

    return () => {
      globalThis.clearTimeout(startTimer);
      marketDataStore.dispose();
    };
  }, []);

  return useSyncExternalStore(
    marketDataStore.subscribe,
    marketDataStore.getSnapshot,
  );
}

export const setMarketTimeframe = marketDataStore.setTimeframe;
