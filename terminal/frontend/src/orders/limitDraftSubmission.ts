import type { Dispatch } from "react";
import type {
  LimitCommandRequest,
  PaperLimitMutationResponse,
  PaperState,
} from "../contracts/trading";
import {
  type LimitDraft,
  type LimitDraftAction,
  type LimitSubmitAttempt,
  LimitDraftSubmitLatch,
} from "./limitDraft";
import { executePaperLimitCommand } from "./paperLimitCommand";

export type LimitDraftSubmissionDependencies = {
  dispatch: Dispatch<LimitDraftAction>;
  createClientActionId: () => string;
  applyPaperState: (state: PaperState) => boolean;
  fetcher?: typeof fetch;
};

export class PaperLimitDraftSubmitController {
  private readonly latches = new Map<
    string,
    LimitDraftSubmitLatch<PaperLimitMutationResponse>
  >();
  private readonly handledAttempts = new WeakSet<object>();

  submit(
    draft: LimitDraft,
    dependencies: LimitDraftSubmissionDependencies,
  ): LimitSubmitAttempt<PaperLimitMutationResponse> {
    const fetcher = dependencies.fetcher ?? fetch;
    let latch = this.latches.get(draft.draftId);
    if (!latch) {
      latch = new LimitDraftSubmitLatch<PaperLimitMutationResponse>();
      this.latches.set(draft.draftId, latch);
    }

    const attempt = latch.submit(
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
        const result = await executePaperLimitCommand(request, {
          fetcher,
          applyPaperState: dependencies.applyPaperState,
        });
        return { certainty: "definitive", value: result };
      },
    );

    if (this.handledAttempts.has(attempt)) return attempt;
    this.handledAttempts.add(attempt);

    dependencies.dispatch({
      type: "start-submitting",
      clientActionId: attempt.clientActionId,
      draftId: attempt.draftId,
    });

    const submission = attempt.promise;
    attempt.promise = submission.then((outcome) => {
      if (outcome.certainty === "ambiguous") {
        dependencies.dispatch({
          type: "mark-ambiguous",
          clientActionId: attempt.clientActionId,
          draftId: attempt.draftId,
        });
        return outcome;
      }

      if (outcome.value.status === "completed") {
        dependencies.dispatch({ type: "dismiss", draftId: attempt.draftId });
        return outcome;
      }

      dependencies.dispatch({
        type: "mark-rejected",
        clientActionId: attempt.clientActionId,
        reason: outcome.value.reason_code,
        draftId: attempt.draftId,
      });
      return outcome;
    });

    return attempt;
  }
}
