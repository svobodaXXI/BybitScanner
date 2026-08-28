import type {
  LimitCommandRequest,
  PaperLimitAmendRequest,
  PaperLimitCancelRequest,
  PaperLimitMutationResponse,
  PaperState,
} from "../contracts/trading";

export async function executePaperLimitAmend(
  request: PaperLimitAmendRequest,
  dependencies: { applyPaperState: (state: PaperState) => boolean; fetcher?: typeof fetch },
) {
  const response = await (dependencies.fetcher ?? fetch)("/api/limit/amend", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
  });
  const result = (await response.json()) as PaperLimitMutationResponse;
  if (result.status === "completed") dependencies.applyPaperState(result.paper_state);
  return result;
}

export async function executePaperLimitCommand(
  request: LimitCommandRequest,
  dependencies: {
    applyPaperState: (state: PaperState) => boolean;
    fetcher?: typeof fetch;
  },
) {
  const response = await (dependencies.fetcher ?? fetch)("/api/limit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const result = (await response.json()) as PaperLimitMutationResponse;
  if (result.status === "completed") {
    dependencies.applyPaperState(result.paper_state);
  }
  return result;
}

export async function executePaperLimitCancel(
  request: PaperLimitCancelRequest,
  dependencies: {
    applyPaperState: (state: PaperState) => boolean;
    fetcher?: typeof fetch;
  },
) {
  const response = await (dependencies.fetcher ?? fetch)("/api/limit/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const result = (await response.json()) as PaperLimitMutationResponse;
  if (result.status === "completed") {
    dependencies.applyPaperState(result.paper_state);
  }
  return result;
}
