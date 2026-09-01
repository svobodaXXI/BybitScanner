import type { LiveMarketCommandRequest, LiveMarketCommandResponse, MarketSide } from "../contracts/trading";

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

export async function executeLiveMarketCommand(
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
