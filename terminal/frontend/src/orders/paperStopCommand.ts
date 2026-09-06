import type {
  PaperState,
  PaperStopDeleteRequest,
  PaperStopMutationRequest,
  PaperStopMutationResponse,
} from "../contracts/trading";
import { ProtectionCommandLifecycleController } from "./protectionCommandLifecycle";

type Dependencies = { applyPaperState: (state: PaperState) => boolean };

const protectionLifecycle =
  new ProtectionCommandLifecycleController<PaperStopMutationResponse>();

const attemptKey = (
  path: string,
  request: PaperStopMutationRequest | PaperStopDeleteRequest,
) => "trigger_price" in request
  ? `${path}:${request.symbol}:${request.trigger_price}`
  : `${path}:${request.symbol}`;

async function dispatch(
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

function execute(
  path: string,
  request: PaperStopMutationRequest | PaperStopDeleteRequest,
  dependencies: Dependencies,
): Promise<PaperStopMutationResponse> {
  return protectionLifecycle.submit(attemptKey(path, request), {
    startAttempt: () => dispatch(path, request, dependencies),
    classifyResult: () => "release",
    releaseOnError: true,
  });
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
