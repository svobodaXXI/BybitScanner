import type {
  PaperState,
  PaperStopDeleteRequest,
  PaperStopMutationRequest,
  PaperStopMutationResponse,
} from "../contracts/trading";

type Dependencies = { applyPaperState: (state: PaperState) => boolean };

async function execute(
  path: string,
  request: PaperStopMutationRequest | PaperStopDeleteRequest,
  dependencies: Dependencies,
): Promise<PaperStopMutationResponse> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const result = (await response.json()) as PaperStopMutationResponse;
  if (!response.ok || result.status !== "completed") {
    throw new Error(result.reason_code || "paper_protection_mutation_failed");
  }
  if (!dependencies.applyPaperState(result.paper_state)) {
    throw new Error("paper_protection_authoritative_state_rejected");
  }
  return result;
}

export const executePaperStopCreate = (
  request: PaperStopMutationRequest,
  dependencies: Dependencies,
) => execute("/api/stop", request, dependencies);

export const executePaperStopAmend = (
  request: PaperStopMutationRequest,
  dependencies: Dependencies,
) => execute("/api/stop/amend", request, dependencies);

export const executePaperStopDelete = (
  request: PaperStopDeleteRequest,
  dependencies: Dependencies,
) => execute("/api/stop/delete", request, dependencies);

export const executePaperTakeCreate = (
  request: PaperStopMutationRequest,
  dependencies: Dependencies,
) => execute("/api/take", request, dependencies);

export const executePaperTakeAmend = (
  request: PaperStopMutationRequest,
  dependencies: Dependencies,
) => execute("/api/take/amend", request, dependencies);

export const executePaperTakeDelete = (
  request: PaperStopDeleteRequest,
  dependencies: Dependencies,
) => execute("/api/take/delete", request, dependencies);
