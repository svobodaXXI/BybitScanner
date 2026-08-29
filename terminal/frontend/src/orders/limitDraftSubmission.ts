import type { Dispatch } from "react";
import type {
  PaperLimitMutationResponse,
  PaperState,
} from "../contracts/trading";
import type {
  LimitDraft,
  LimitDraftAction,
  LimitSubmitAttempt,
} from "./limitDraft";
import { PaperLimitCreateController } from "./paperLimitCreate";

export type LimitDraftSubmissionDependencies = {
  dispatch: Dispatch<LimitDraftAction>;
  createClientActionId: () => string;
  applyPaperState: (state: PaperState) => boolean;
  fetcher?: typeof fetch;
};

export class PaperLimitDraftSubmitController {
  private readonly creates = new PaperLimitCreateController();
  private readonly attempts = new Map<
    string,
    LimitSubmitAttempt<PaperLimitMutationResponse>
  >();
  private readonly handledAttempts = new WeakSet<object>();

  submit(
    draft: LimitDraft,
    dependencies: LimitDraftSubmissionDependencies,
  ): LimitSubmitAttempt<PaperLimitMutationResponse> {
    const fetcher = dependencies.fetcher ?? fetch;
    const existing = this.attempts.get(draft.draftId);
    if (existing) return existing;
    const createAttempt = this.creates.submit(
      draft.draftId,
      {
        symbol: draft.symbol,
        side: draft.side,
        volume: draft.volume,
        sizingReferencePrice: draft.sizingReferencePrice,
        price: draft.price,
        authoritativeTickSize: draft.authoritativeTickSize,
      },
      {
        createClientActionId: dependencies.createClientActionId,
        applyPaperState: dependencies.applyPaperState,
        fetcher,
      },
    );
    const attempt: LimitSubmitAttempt<PaperLimitMutationResponse> = {
      draftId: draft.draftId,
      clientActionId: createAttempt.clientActionId,
      promise: createAttempt.promise,
    };
    this.attempts.set(draft.draftId, attempt);

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
        this.attempts.delete(attempt.draftId);
        dependencies.dispatch({ type: "dismiss", draftId: attempt.draftId });
        return outcome;
      }

      dependencies.dispatch({
        type: "mark-rejected",
        clientActionId: attempt.clientActionId,
        reason: outcome.value.reason_code,
        draftId: attempt.draftId,
      });
      this.attempts.delete(attempt.draftId);
      return outcome;
    });

    return attempt;
  }
}
