import type {
  LimitCommandRequest,
  MarketSide,
  PaperLimitAmendRequest,
  PaperLimitCancelRequest,
  PaperLimitOrder,
  VolumeRequest,
} from "../contracts/trading";

export type LiveAuthority = { accountId: string; sessionGeneration: number };
export type LiveLimitResponse = {
  status: string;
  reason_code: string;
  command_id: string | null;
  reconciliation_required: boolean;
};

type AuthorityFields = { account_id: string; session_generation: number };

async function execute<T extends object>(
  path: string,
  request: T & AuthorityFields,
  currentAuthority: () => LiveAuthority | null,
  fetcher: typeof fetch = fetch,
): Promise<LiveLimitResponse | null> {
  const response = await fetcher(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const result = await response.json() as LiveLimitResponse;
  const current = currentAuthority();
  if (!current || current.accountId !== request.account_id
    || current.sessionGeneration !== request.session_generation) return null;
  return result;
}

export const executeLiveLimitCreate = (
  request: LimitCommandRequest & AuthorityFields,
  currentAuthority: () => LiveAuthority | null,
  fetcher?: typeof fetch,
) => execute("/api/live/limit", request, currentAuthority, fetcher);

export const executeLiveLimitAmend = (
  request: PaperLimitAmendRequest & AuthorityFields,
  currentAuthority: () => LiveAuthority | null,
  fetcher?: typeof fetch,
) => execute("/api/live/limit/amend", request, currentAuthority, fetcher);

export const executeLiveLimitCancel = (
  request: PaperLimitCancelRequest & AuthorityFields,
  currentAuthority: () => LiveAuthority | null,
  fetcher?: typeof fetch,
) => execute("/api/live/limit/cancel", request, currentAuthority, fetcher);

export function projectLiveLimitOrders(
  orders: Array<Record<string, unknown>>,
  symbol: string,
): PaperLimitOrder[] {
  return orders.flatMap((order) => {
    if (order.symbol !== symbol || order.order_type !== "Limit"
      || typeof order.order_id !== "string" || typeof order.side !== "string"
      || !["Buy", "Sell"].includes(order.side)
      || typeof order.price !== "string" || typeof order.quantity !== "string") return [];
    return [{
      order_id: order.order_id,
      order_link_id: "",
      symbol,
      side: order.side as MarketSide,
      price: order.price,
      quantity: order.quantity,
      time_in_force: "GTC",
    }];
  });
}

export function liveLimitCreateRequest(input: {
  authority: LiveAuthority;
  clientActionId: string;
  symbol: string;
  side: MarketSide;
  volume: VolumeRequest;
  sizingReferencePrice: string;
  limitPrice: string;
}): LimitCommandRequest & AuthorityFields {
  return {
    client_action_id: input.clientActionId,
    account_id: input.authority.accountId,
    session_generation: input.authority.sessionGeneration,
    symbol: input.symbol,
    side: input.side,
    volume: input.volume,
    sizing_reference_price: input.sizingReferencePrice,
    limit_price: input.limitPrice,
    time_in_force: "GTC",
  };
}
