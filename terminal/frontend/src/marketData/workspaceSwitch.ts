export interface WorkspaceSemanticFailure {
  code: string;
  stage: string;
  requested_symbol: string | null;
  active_symbol: string | null;
  retryable: boolean;
  request_id: string | null;
  message: string;
}

export type WorkspaceActivationResult =
  | { ok: true; symbol: string; generation: number }
  | { ok: false; error: WorkspaceSemanticFailure };

const record = (value: unknown): Record<string, unknown> | null => (
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
);

const semanticFailure = (
  value: unknown,
  requestedSymbol: string,
): WorkspaceSemanticFailure | null => {
  const error = record(value);
  if (
    !error || typeof error.code !== "string" || typeof error.stage !== "string"
    || typeof error.retryable !== "boolean" || typeof error.message !== "string"
  ) return null;
  return {
    code: error.code,
    stage: error.stage,
    requested_symbol: typeof error.requested_symbol === "string"
      ? error.requested_symbol : requestedSymbol,
    active_symbol: typeof error.active_symbol === "string" ? error.active_symbol : null,
    retryable: error.retryable,
    request_id: typeof error.request_id === "string" ? error.request_id : null,
    message: error.message,
  };
};

const boundaryFailure = (
  requestedSymbol: string,
  message: string,
): WorkspaceSemanticFailure => ({
  code: "upstream_market_data_failure",
  stage: "workspace_activation_ack",
  requested_symbol: requestedSymbol,
  active_symbol: null,
  retryable: true,
  request_id: null,
  message,
});

export async function requestWorkspaceActivation(
  requestedSymbol: string,
  route: string,
  fetcher: typeof fetch = fetch,
): Promise<WorkspaceActivationResult> {
  const normalized = requestedSymbol.trim().toUpperCase();
  try {
    const response = await fetcher(route, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: normalized }),
    });
    const payload = record(await response.json());
    if (!response.ok || payload?.ok !== true) {
      return {
        ok: false,
        error: semanticFailure(payload?.workspace_error, normalized)
          ?? boundaryFailure(normalized, "Workspace activation failed without a semantic error envelope"),
      };
    }
    const generation = Number(payload.generation);
    if (
      payload.symbol !== normalized || !Number.isInteger(generation) || generation <= 0
    ) {
      return {
        ok: false,
        error: boundaryFailure(normalized, "Workspace activation acknowledgement is invalid"),
      };
    }
    return { ok: true, symbol: normalized, generation };
  } catch {
    return {
      ok: false,
      error: boundaryFailure(normalized, "Workspace activation request failed"),
    };
  }
}
