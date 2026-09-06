import type {
  CommandMutationResponse,
  MarketCommandRequest,
  MarketSide,
  PaperState,
} from "../contracts/trading";
import { MarketCommandLifecycleController } from "./marketCommandLifecycle";

type PaperMarketCommandDependencies = {
  applyPaperState?: (state: PaperState) => boolean;
  fetcher?: typeof fetch;
};

const paperMarketLifecycle =
  new MarketCommandLifecycleController<CommandMutationResponse>();

async function dispatchPaperMarketCommand(
  request: MarketCommandRequest,
  dependencies: PaperMarketCommandDependencies,
): Promise<CommandMutationResponse> {
  const fetcher = dependencies.fetcher ?? fetch;
  const response = await fetcher("/api/market", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });

  const result = (await response.json()) as CommandMutationResponse;

  if (result.status === "completed") {
    dependencies.applyPaperState?.(result.paper_state);
  }

  return result;
}

export function executePaperMarketCommand(
  request: MarketCommandRequest,
  dependencies: PaperMarketCommandDependencies = {},
): Promise<CommandMutationResponse> {
  return paperMarketLifecycle.submit(request.client_action_id, {
    startAttempt: () => dispatchPaperMarketCommand(request, dependencies),
    classifyResult: () => "release",
    releaseOnError: true,
  });
}

export function domSelectionRequiresMarket(
  side: MarketSide,
  normalizedPrice: string,
  bestBid: number | undefined,
  bestAsk: number | undefined,
): boolean {
  const price = Number(normalizedPrice);
  if (!Number.isFinite(price)) return false;

  if (side === "Buy") {
    return bestAsk !== undefined && price >= bestAsk;
  }

  return bestBid !== undefined && price <= bestBid;
}
