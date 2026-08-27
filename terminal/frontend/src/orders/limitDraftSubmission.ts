import type { Dispatch } from "react";
import type {
  LimitCommandRequest,
  PaperLimitMutationResult,
} from "../contracts/trading";
import {
  type LimitDraft,
  type LimitDraftAction,
  type LimitSubmitAttempt,
  LimitDraftSubmitLatch,
} from "./limitDraft";

export type LimitDraftSubmissionDependencies = {
  dispatch: Dispatch<LimitDraftAction>;
  createClientActionId: () => string;
  refreshPaperState: () => Promise<void>;
  fetcher?: typeof fetch;
};

export class PaperLimitDraftSubmitController {
  private readonly latch = new LimitDraftSubmitLatch<PaperLimitMutationResult>();
  private readonly handled = new Set<string>();

  submit(
    draft: LimitDraft,
    dependencies: LimitDraftSubmissionDependencies,
  ): LimitSubmitAttempt<PaperLimitMutationResult> {
    const fetcher = dependencies.fetcher ?? fetch;
    const attempt = this.latch.submit(
      draft,
      dependencies.createClientActionId,
      async (submittingDraft) => {
        const request: LimitCommandRequest = {
          client_action_id: submittingDraft.clientActionId!,
          symbol: submittingDraft.symbol,
          side: submittingDraft.side,
          volume: submittingDraft.volume,
          sizing_reference_price: submittingDraft.sizingReferencePrice,
          limit_price: submittingDraft.price,
          time_in_force: "GTC",
        };
        const response = await fetcher("/api/limit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });
        const result = (await response.json()) as PaperLimitMutationResult;
        return { certainty: "definitive", value: result };
      },
    );

    dependencies.dispatch({
      type: "start-submitting",
      clientActionId: attempt.clientActionId,
    });

    if (!this.handled.has(attempt.clientActionId)) {
      this.handled.add(attempt.clientActionId);
      void attempt.promise.then(async (outcome) => {
        if (outcome.certainty === "ambiguous") {
          dependencies.dispatch({
            type: "mark-ambiguous",
            clientActionId: attempt.clientActionId,
          });
          return;
        }

        if (outcome.value.status === "completed") {
          dependencies.dispatch({ type: "dismiss" });
          await dependencies.refreshPaperState();
          this.handled.delete(attempt.clientActionId);
          return;
        }

        dependencies.dispatch({
          type: "mark-rejected",
          clientActionId: attempt.clientActionId,
          reason: outcome.value.reason_code,
        });
        this.handled.delete(attempt.clientActionId);
      });
    }

    return attempt;
  }
}
