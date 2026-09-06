import type { LiveAuthority } from "./liveLimitCommand";

export type LiveFullCloseRequest = {
  client_action_id: string;
  account_id: string;
  session_generation: number;
  symbol: string;
};

export type LiveFullCloseResponse = {
  status: string;
  reason_code: string;
  command_id: string | null;
  reconciliation_required: boolean;
};

export async function executeLiveFullClose(
  request: LiveFullCloseRequest,
  currentAuthority: () => LiveAuthority | null,
  fetcher: typeof fetch = fetch,
): Promise<LiveFullCloseResponse | null> {
  const response = await fetcher("/api/live/full-close", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const result = await response.json() as LiveFullCloseResponse;
  const current = currentAuthority();
  if (
    !current
    || current.accountId !== request.account_id
    || current.sessionGeneration !== request.session_generation
  ) return null;
  return result;
}
