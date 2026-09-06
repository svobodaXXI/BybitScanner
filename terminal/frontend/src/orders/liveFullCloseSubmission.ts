import { FullCloseCommandLifecycleController } from "./fullCloseCommandLifecycle";
import {
  executeLiveFullClose,
  type LiveFullCloseResponse,
} from "./liveFullCloseCommand";
import type { LiveAuthority } from "./liveLimitCommand";

type Input = {
  symbol: string;
};

type Dependencies = {
  currentAuthority: () => LiveAuthority | null;
  createClientActionId?: () => string;
  refreshActiveLive: () => Promise<void>;
};

const createDefaultClientActionId = () => `live-full-close-${Date.now()}`;

export class LiveFullCloseSubmissionController {
  private readonly lifecycle = new FullCloseCommandLifecycleController<LiveFullCloseResponse | null>();

  submit(input: Input, dependencies: Dependencies): Promise<LiveFullCloseResponse | null> {
    const attemptKey = `FULL_CLOSE:${input.symbol}`;
    return this.lifecycle.submit(attemptKey, {
      startAttempt: async () => {
        const authority = dependencies.currentAuthority();
        if (!authority) throw new Error("stale_live_authority");
        const clientActionId = (dependencies.createClientActionId ?? createDefaultClientActionId)();
        const result = await executeLiveFullClose(
          {
            client_action_id: clientActionId,
            account_id: authority.accountId,
            session_generation: authority.sessionGeneration,
            symbol: input.symbol,
          },
          dependencies.currentAuthority,
        );
        if (result?.status === "accepted_pending" || result?.status === "completed") {
          await dependencies.refreshActiveLive();
        }
        return result;
      },
      classifyResult: (result) => {
        if (result === null) return "retain";
        if (result.status === "unknown" || result.reconciliation_required) return "retain";
        return "release";
      },
      releaseOnError: false,
    });
  }

  clear(): void {
    this.lifecycle.clear();
  }
}
