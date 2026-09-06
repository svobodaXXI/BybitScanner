import type {
  CommandMutationResponse,
  FullCloseCommandRequest,
  PaperState,
} from "../contracts/trading";

type Dependencies = {
  applyPaperState?: (state: PaperState) => boolean;
  fetchImpl?: typeof fetch;
};

export async function executePaperFullCloseCommand(
  request: FullCloseCommandRequest,
  dependencies: Dependencies = {},
): Promise<CommandMutationResponse> {
  const fetchImpl = dependencies.fetchImpl ?? fetch;
  const response = await fetchImpl("/api/full-close", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const result = (await response.json()) as CommandMutationResponse;
  if (result.status === "completed" && dependencies.applyPaperState) {
    if (!dependencies.applyPaperState(result.paper_state)) {
      throw new Error("paper_full_close_authoritative_state_rejected");
    }
  }
  return result;
}
