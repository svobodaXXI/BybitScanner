import type { PaperState, PaperStopMutationResponse } from "../contracts/trading";
import {
  clearPaperProtectionCommandLifecycle,
  executePaperStopAmend,
  executePaperStopCreate,
  executePaperStopDelete,
  executePaperTakeAmend,
  executePaperTakeCreate,
  executePaperTakeDelete,
} from "./paperStopCommand";
import { ProtectionCommandLifecycleController } from "./protectionCommandLifecycle";

export type ProtectionLeg = "STOP" | "TAKE";
export type ProtectionOperation = "CREATE" | "AMEND" | "DELETE";

type Input = {
  leg: ProtectionLeg;
  operation: ProtectionOperation;
  symbol: string;
  triggerPrice?: string;
};

type Dependencies = {
  createClientActionId: () => string;
  applyPaperState: (state: PaperState) => boolean;
  runMutation: (
    actionKey: string,
    mutation: () => Promise<PaperStopMutationResponse>,
  ) => Promise<PaperStopMutationResponse>;
};

const attemptKey = (input: Input) => input.operation === "DELETE"
  ? `${input.leg}:${input.operation}:${input.symbol}`
  : `${input.leg}:${input.operation}:${input.symbol}:${input.triggerPrice ?? ""}`;

export class PaperProtectionMutationController {
  private readonly lifecycle =
    new ProtectionCommandLifecycleController<PaperStopMutationResponse>();

  submit(input: Input, dependencies: Dependencies): Promise<PaperStopMutationResponse> {
    return this.lifecycle.submit(attemptKey(input), {
      startAttempt: () => {
        const clientActionId = dependencies.createClientActionId();
        const actionKey = `${input.operation}_${input.leg}:${clientActionId}`;

        if (input.operation === "DELETE") {
          const execute = input.leg === "STOP"
            ? executePaperStopDelete
            : executePaperTakeDelete;
          return dependencies.runMutation(actionKey, () => execute({
            client_action_id: clientActionId,
            symbol: input.symbol,
          }, { applyPaperState: dependencies.applyPaperState }));
        }

        const execute = input.leg === "STOP"
          ? input.operation === "CREATE" ? executePaperStopCreate : executePaperStopAmend
          : input.operation === "CREATE" ? executePaperTakeCreate : executePaperTakeAmend;
        return dependencies.runMutation(actionKey, () => execute({
          client_action_id: clientActionId,
          symbol: input.symbol,
          trigger_price: input.triggerPrice ?? "",
        }, { applyPaperState: dependencies.applyPaperState }));
      },
      classifyResult: () => "release",
      releaseOnError: true,
    });
  }

  clear(): void {
    this.lifecycle.clear();
    clearPaperProtectionCommandLifecycle();
  }
}
