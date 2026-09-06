import type { LiveAuthority } from "./liveLimitCommand";

export type LiveProtectionOperation = "CREATE" | "AMEND" | "DELETE";
export type LiveProtectionLeg = "STOP" | "TAKE";

export type LiveProtectionRequest = {
  client_action_id: string;
  account_id: string;
  session_generation: number;
  symbol: string;
  take_profit: string | null;
  stop_loss: string | null;
  tp_trigger_by: "MarkPrice";
  sl_trigger_by: "MarkPrice";
};

export type LiveProtectionResponse = {
  status: string;
  reason_code: string;
  command_id: string | null;
  reconciliation_required: boolean;
};

const protectionPath = (
  leg: LiveProtectionLeg,
  operation: LiveProtectionOperation,
) => {
  const base = leg === "STOP" ? "/api/live/stop" : "/api/live/take";
  if (operation === "CREATE") return base;
  if (operation === "AMEND") return `${base}/amend`;
  return `${base}/delete`;
};

export async function executeLiveProtection(
  leg: LiveProtectionLeg,
  operation: LiveProtectionOperation,
  request: LiveProtectionRequest,
  currentAuthority: () => LiveAuthority | null,
  fetcher: typeof fetch = fetch,
): Promise<LiveProtectionResponse | null> {
  const response = await fetcher(protectionPath(leg, operation), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const result = await response.json() as LiveProtectionResponse;
  const current = currentAuthority();
  if (
    !current
    || current.accountId !== request.account_id
    || current.sessionGeneration !== request.session_generation
  ) return null;
  return result;
}
