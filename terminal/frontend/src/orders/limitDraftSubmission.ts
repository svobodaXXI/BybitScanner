import type { Dispatch } from "react";
import type {
  PaperLimitMutationResponse,
  PaperState,
} from "../contracts/trading";
import type {
  LimitDraft,
  LimitDraftAction,
  LimitSubmitAttempt,
  LimitSubmitOutcome,
} from "./limitDraft";
import { PaperLimitCreateController } from "./paperLimitCreate";

export type LimitDraftSubmissionDisposition =
  | { state: "completed" }
  | { state: "rejected"; reason: string }
  | { state: "ambiguous" };

export type LimitDraftSubmitBoundaryDependencies<T> = {
  dispatch: Dispatch<LimitDraftAction>;
  startAttempt: (draft: LimitDraft) => LimitSubmitAttempt<T>;
  classifyOutcome: (
    outcome: LimitSubmitOutcome<T>,
  ) => LimitDraftSubmissionDisposition;
};

/**
 * Owns the provider-independent Limit draft submission lifecycle.
 *
 * Execution adapters remain responsible for transport, authority fencing and
 * command identity. This controller owns only the common draft semantics:
 * one attempt per draft, submitting -> completed/rejected/ambiguous, and the
 * corresponding reducer actions.
 */
export class LimitDraftSubmitController<T> {
  private readonly attempts = new Map<string, LimitSubmitAttempt<T>>();

  submit(
    draft: LimitDraft,
    dependencies: LimitDraftSubmitBoundaryDependencies<T>,
  ): LimitSubmitAttempt<T> {
    const existing = this.attempts.get(draft.draftId);
    if (existing) return existing;

    // startAttempt may fail closed during provider-specific preflight. Keep
    // that failure outside the shared lifecycle so a blocked command is not
    // incorrectly marked as having entered transport.
    const attempt = dependencies.startAttempt(draft);
    this.attempts.set(draft.draftId, attempt);

    dependencies.dispatch({
      type: "start-submitting",
      clientActionId: attempt.clientActionId,
      draftId: attempt.draftId,
    });

    const submission = attempt.promise;
    attempt.promise = submission.then((outcome) => {
      const disposition = dependencies.classifyOutcome(outcome);

      if (disposition.state === "ambiguous") {
        dependencies.dispatch({
          type: "mark-ambiguous",
          clientActionId: attempt.clientActionId,
          draftId: attempt.draftId,
        });
        return outcome;
      }

      this.attempts.delete(attempt.draftId);

      if (disposition.state === "completed") {
        dependencies.dispatch({ type: "dismiss", draftId: attempt.draftId });
        return outcome;
      }

      dependencies.dispatch({
        type: "mark-rejected",
        clientActionId: attempt.clientActionId,
        reason: disposition.reason,
        draftId: attempt.draftId,
      });
      return outcome;
    });

    return attempt;
  }
}

export type LimitDraftSubmissionDependencies = {
  dispatch: Dispatch<LimitDraftAction>;
  createClientActionId: () => string;
  applyPaperState: (state: PaperState) => boolean;
  fetcher?: typeof fetch;
};

function classifyPaperLimitOutcome(
  outcome: LimitSubmitOutcome<PaperLimitMutationResponse>,
): LimitDraftSubmissionDisposition {
  if (outcome.certainty === "ambiguous") return { state: "ambiguous" };
  if (outcome.value.status === "completed") return { state: "completed" };
  return { state: "rejected", reason: outcome.value.reason_code };
}

/**
 * PAPER adapter for the shared draft lifecycle. Kept as the existing public
 * controller so App callers do not change while LIVE is migrated behind the
 * same boundary in the next step.
 */
export class PaperLimitDraftSubmitController {
  private readonly common = new LimitDraftSubmitController<PaperLimitMutationResponse>();
  private readonly creates = new PaperLimitCreateController();

  submit(
    draft: LimitDraft,
    dependencies: LimitDraftSubmissionDependencies,
  ): LimitSubmitAttempt<PaperLimitMutationResponse> {
    const fetcher = dependencies.fetcher ?? fetch;
    return this.common.submit(draft, {
      dispatch: dependencies.dispatch,
      startAttempt: (candidate) => {
        const createAttempt = this.creates.submit(
          candidate.draftId,
          {
            symbol: candidate.symbol,
            side: candidate.side,
            volume: candidate.volume,
            sizingReferencePrice: candidate.sizingReferencePrice,
            price: candidate.price,
            authoritativeTickSize: candidate.authoritativeTickSize,
          },
          {
            createClientActionId: dependencies.createClientActionId,
            applyPaperState: dependencies.applyPaperState,
            fetcher,
          },
        );
        return {
          draftId: candidate.draftId,
          clientActionId: createAttempt.clientActionId,
          promise: createAttempt.promise,
        };
      },
      classifyOutcome: classifyPaperLimitOutcome,
    });
  }
}
