import type { PaperState, PaperStopMutationResponse } from "../contracts/trading";
import {
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
  runMutation: <T>(actionKey: string, mutation: () => Promise<T>) => Promise<T>;
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
        const execute = input.leg === "STOP"
          ? input.operation === "CREATE" ? executePaperStopCreate
            : input.operation === "AMEND" ? executePaperStopAmend
              : executePaperStopDelete
          : input.operation === "CREATE" ? executePaperTakeCreate
            : input.operation === "AMEND" ? executePaperTakeAmend
              : executePaperTakeDelete;

        const request = input.operation === "DELETE"
          ? { client_action_id: clientActionId, symbol: input.symbol }
          : {
              client_action_id: clientActionId,
              symbol: input.symbol,
              trigger_price: input.triggerPrice ?? "",
            };

        return dependencies.runMutation(
          `${input.operation}_${input.leg}:${clientActionId}`,
          () => execute(request, { applyPaperState: dependencies.applyPaperState }),
        );
      },
      classifyResult: () => "release",
      releaseOnError: true,
    });
  }

  clear(): void {
    this.lifecycle.clear();
  }
}
