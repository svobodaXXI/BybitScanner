import { useEffect, useSyncExternalStore } from "react";
import { marketApiRoutes } from "./apiRoutes";
import { marketDataStore } from "./marketDataStore";

type WorkspaceStateResponse = {
  ok?: boolean;
  workspace?: {
    active_symbol?: string | null;
    active_generation?: number | null;
  };
};

export function useMarketData() {
  useEffect(() => {
    const controller = new AbortController();

    const start = async () => {
      try {
        const response = await fetch(marketApiRoutes.workspaceState, {
          signal: controller.signal,
        });
        const payload = await response.json() as WorkspaceStateResponse;
        const symbol = payload.workspace?.active_symbol;
        const generation = payload.workspace?.active_generation;
        if (
          response.ok
          && payload.ok
          && typeof symbol === "string"
          && symbol.trim()
          && Number.isInteger(generation)
          && Number(generation) > 0
        ) {
          marketDataStore.setSymbol(symbol, Number(generation));
        }
      } catch {
        if (controller.signal.aborted) return;
      }

      if (!controller.signal.aborted) marketDataStore.start();
    };

    void start();

    return () => {
      controller.abort();
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
