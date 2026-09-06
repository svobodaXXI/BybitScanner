import type { Dispatch } from "react";
import type {
  LimitDraft,
  LimitDraftAction,
  LimitSubmitAttempt,
  LimitSubmitOutcome,
} from "./limitDraft";
import { normalizedLimitDraftPrice } from "./limitDraft";
import {
  type LiveAuthority,
  type LiveLimitResponse,
  executeLiveLimitCreate,
  liveLimitCreateRequest,
} from "./liveLimitCommand";
import {
  LimitDraftSubmitController,
  type LimitDraftSubmissionDisposition,
} from "./limitDraftSubmission";

export type LiveLimitDraftSubmissionDependencies = {
  dispatch: Dispatch<LimitDraftAction>;
  currentAuthority: () => LiveAuthority | null;
  createClientActionId: () => string;
  refreshActiveLive: () => Promise<unknown>;
  fetcher?: typeof fetch;
};

function classifyLiveLimitOutcome(
  outcome: LimitSubmitOutcome<LiveLimitResponse>,
): LimitDraftSubmissionDisposition {
  if (outcome.certainty === "ambiguous") return { state: "ambiguous" };

  const result = outcome.value;
  if (result.status === "accepted_pending" || result.status === "completed") {
    return { state: "completed" };
  }
  if (result.status === "unknown" || result.reconciliation_required) {
    return { state: "ambiguous" };
  }
  return { state: "rejected", reason: result.reason_code };
}

/**
 * LIVE execution adapter for the provider-independent Limit draft lifecycle.
 *
 * The common controller owns draft transitions and one-attempt-per-draft
 * semantics. This adapter retains LIVE-only authority fencing, durable command
 * identity, exchange transport, UNKNOWN handling and authoritative refresh.
 */
export class LiveLimitDraftSubmitController {
  private readonly common = new LimitDraftSubmitController<LiveLimitResponse>();
  private readonly refreshHandled = new WeakSet<object>();

  submit(
    draft: LimitDraft,
    dependencies: LiveLimitDraftSubmissionDependencies,
  ): LimitSubmitAttempt<LiveLimitResponse> {
    const attempt = this.common.submit(draft, {
      dispatch: dependencies.dispatch,
      startAttempt: (candidate) => {
        const authority = dependencies.currentAuthority();
        const normalizedPrice = normalizedLimitDraftPrice(candidate);
        if (!authority || normalizedPrice === null) {
          throw new Error("current LIVE authority and valid Limit price are required");
        }

        const clientActionId = dependencies.createClientActionId();
        const promise: Promise<LimitSubmitOutcome<LiveLimitResponse>> =
          executeLiveLimitCreate(
            liveLimitCreateRequest({
              authority,
              clientActionId,
              symbol: candidate.symbol,
              side: candidate.side,
              volume: candidate.volume,
              sizingReferencePrice: candidate.sizingReferencePrice,
              limitPrice: normalizedPrice,
            }),
            dependencies.currentAuthority,
            dependencies.fetcher,
          ).then(
            (result): LimitSubmitOutcome<LiveLimitResponse> =>
              result === null
                ? { certainty: "ambiguous" }
                : { certainty: "definitive", value: result },
            (error: unknown): LimitSubmitOutcome<LiveLimitResponse> => ({
              certainty: "ambiguous",
              error,
            }),
          );

        return {
          draftId: candidate.draftId,
          clientActionId,
          promise,
        };
      },
      classifyOutcome: classifyLiveLimitOutcome,
    });

    if (!this.refreshHandled.has(attempt)) {
      this.refreshHandled.add(attempt);
      const lifecycle = attempt.promise;
      attempt.promise = lifecycle.then(async (outcome) => {
        if (
          outcome.certainty === "definitive" &&
          (outcome.value.status === "accepted_pending" ||
            outcome.value.status === "completed")
        ) {
          await dependencies.refreshActiveLive();
        }
        return outcome;
      });
    }

    return attempt;
  }
}
