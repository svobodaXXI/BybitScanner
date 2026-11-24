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
let finishPendingBootstrap: (() => void) | null = null;
export const setMarketSymbol = (symbol: string, generation?: number) => {
  confirmedSymbolIntentRevision += 1;
  marketDataStore.setSymbol(symbol, generation);
  // A validated activation ACK supplies the same symbol/generation authority
  // as bootstrap. Do not wait for the now superseded state request.
  if (Number.isInteger(generation) && Number(generation) > 0) finishPendingBootstrap?.();
};

export function useMarketData() {
  useEffect(() => {
    const controller = new AbortController();
    const bootstrapRevision = confirmedSymbolIntentRevision;
    const finish = () => {
      if (controller.signal.aborted) return;
      if (finishPendingBootstrap === finish) finishPendingBootstrap = null;
      controller.abort();
      marketDataStore.start();
    };
    finishPendingBootstrap = finish;

    const start = async () => {
      try {
        const response = await fetch(marketApiRoutes.workspaceState, {
          signal: controller.signal,
        });
        const payload = await response.json() as WorkspaceStateResponse;
        const symbol = payload.workspace?.active_symbol;
        const generation = payload.workspace?.active_generation;
        if (
          !controller.signal.aborted
          && response.ok
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

      finish();
    };

    void start();

    return () => {
      if (finishPendingBootstrap === finish) finishPendingBootstrap = null;
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
