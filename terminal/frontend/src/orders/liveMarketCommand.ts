import type { LiveMarketCommandRequest, LiveMarketCommandResponse, MarketSide } from "../contracts/trading";
import { MarketCommandLifecycleController } from "./marketCommandLifecycle";

const liveMarketLifecycle =
  new MarketCommandLifecycleController<LiveMarketCommandResponse | null>();
let liveMarketAuthorityKey: string | null = null;

function marketAuthorityKey(request: LiveMarketCommandRequest): string {
  return `${request.account_id}:${request.session_generation}`;
}

export function createLiveMarketAction(input: {
  accountId: string; sessionGeneration: number; symbol: string; side: MarketSide;
  amount: string; sizingReferencePrice: string; idFactory?: () => string;
}): LiveMarketCommandRequest {
  const idFactory = input.idFactory ?? (() => globalThis.crypto?.randomUUID?.() ?? `live-market-${Date.now()}`);
  return {
    client_action_id: idFactory(), account_id: input.accountId,
    session_generation: input.sessionGeneration, symbol: input.symbol, side: input.side,
    volume: { unit: "usdt", amount: input.amount },
    sizing_reference_price: input.sizingReferencePrice,
    slippage_type: "Percent", slippage_value: "0.5",
  };
}

async function dispatchLiveMarketCommand(
  request: LiveMarketCommandRequest,
  dependencies: {
    fetcher?: typeof fetch;
    currentAuthority: () => { accountId: string; sessionGeneration: number } | null;
  },
): Promise<LiveMarketCommandResponse | null> {
  const response = await (dependencies.fetcher ?? fetch)("/api/live/market", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const result = await response.json() as LiveMarketCommandResponse;
  const current = dependencies.currentAuthority();
  if (!current || current.accountId !== request.account_id
    || current.sessionGeneration !== request.session_generation) return null;
  return result;
}

export function executeLiveMarketCommand(
  request: LiveMarketCommandRequest,
  dependencies: {
    fetcher?: typeof fetch;
    currentAuthority: () => { accountId: string; sessionGeneration: number } | null;
  },
): Promise<LiveMarketCommandResponse | null> {
  const authorityKey = marketAuthorityKey(request);
  if (liveMarketAuthorityKey !== authorityKey) {
    liveMarketLifecycle.clear();
    liveMarketAuthorityKey = authorityKey;
  }

  return liveMarketLifecycle.submit(request.client_action_id, {
    startAttempt: () => dispatchLiveMarketCommand(request, dependencies),
    classifyResult: (result) => {
      if (result === null) return "retain";
      if (result.status === "unknown" || result.reconciliation_required) return "retain";
      if (result.status === "accepted_pending") return "retain";
      return "release";
    },
    releaseOnError: false,
  });
}
