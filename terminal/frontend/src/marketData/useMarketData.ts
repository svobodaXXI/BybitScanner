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

// A confirmed workspace activation outranks an older in-flight bootstrap GET.
// Otherwise a slow /workspace/state response can undo a Telegram deep-link ACK.
let confirmedSymbolIntentRevision = 0;
export const setMarketSymbol = (symbol: string, generation?: number) => {
  confirmedSymbolIntentRevision += 1;
  marketDataStore.setSymbol(symbol, generation);
};

export function useMarketData() {
  useEffect(() => {
    const controller = new AbortController();
    const bootstrapRevision = confirmedSymbolIntentRevision;

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
          && bootstrapRevision === confirmedSymbolIntentRevision
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
