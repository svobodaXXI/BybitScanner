import type {
  CommandMutationResponse,
  PaperState,
} from "../contracts/trading";
import { FullCloseCommandLifecycleController } from "./fullCloseCommandLifecycle";
import { executePaperFullCloseCommand } from "./paperFullCloseCommand";

type Input = {
  symbol: string;
};

type Dependencies = {
  createClientActionId: () => string;
  applyPaperState: (state: PaperState) => boolean;
  runMutation: <T>(key: string, mutation: () => Promise<T>) => Promise<T>;
};

export class PaperFullCloseSubmissionController {
  private readonly lifecycle = new FullCloseCommandLifecycleController<CommandMutationResponse>();

  submit(input: Input, dependencies: Dependencies): Promise<CommandMutationResponse> {
    const attemptKey = `FULL_CLOSE:${input.symbol}`;
    return this.lifecycle.submit(attemptKey, {
      startAttempt: () => {
        const clientActionId = dependencies.createClientActionId();
        return dependencies.runMutation("FULL_CLOSE", () =>
          executePaperFullCloseCommand(
            {
              client_action_id: clientActionId,
              symbol: input.symbol,
            },
            { applyPaperState: dependencies.applyPaperState },
          ),
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
