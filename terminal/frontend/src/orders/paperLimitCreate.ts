import type {
  LimitCommandRequest,
  MarketSide,
  PaperLimitMutationResponse,
  PaperState,
  VolumeRequest,
} from "../contracts/trading";
import { normalizeLimitDraftPrice } from "./limitDraft";
import { executePaperLimitCommand } from "./paperLimitCommand";
import { isValidSelectedVolume } from "./selectedVolume";

export type PaperLimitCreateIntent = {
  symbol: string;
  side: MarketSide;
  volume: VolumeRequest;
  sizingReferencePrice: string;
  price: string;
  authoritativeTickSize: string | null;
};

export type PaperLimitCreateOutcome =
  | { certainty: "definitive"; value: PaperLimitMutationResponse }
  | { certainty: "ambiguous"; error?: unknown };

export type PaperLimitCreateAttempt = {
  intentId: string;
  clientActionId: string;
  promise: Promise<PaperLimitCreateOutcome>;
};

type PaperLimitCreateDependencies = {
  createClientActionId: () => string;
  applyPaperState: (state: PaperState) => boolean;
  fetcher?: typeof fetch;
};

export function normalizedPaperLimitCreatePrice(
  intent: PaperLimitCreateIntent,
): string | null {
  if (!isValidSelectedVolume(intent.volume.amount)) {
    return null;
  }
  return normalizeLimitDraftPrice(
    intent.price,
    intent.authoritativeTickSize,
    intent.side,
  );
}

function buildRequest(
  intent: PaperLimitCreateIntent,
  normalizedPrice: string,
  clientActionId: string,
): LimitCommandRequest {
  return {
    client_action_id: clientActionId,
    symbol: intent.symbol,
    side: intent.side,
    volume: intent.volume,
    sizing_reference_price: intent.sizingReferencePrice,
    limit_price: normalizedPrice,
    time_in_force: "GTC",
  };
}

/** Owns stable command identity and exactly-once transport for each semantic intent. */
export class PaperLimitCreateController {
  private readonly attempts = new Map<string, PaperLimitCreateAttempt>();

  submit(
    intentId: string,
    intent: PaperLimitCreateIntent,
    dependencies: PaperLimitCreateDependencies,
  ): PaperLimitCreateAttempt {
    const existing = this.attempts.get(intentId);
    if (existing) return existing;

    const normalizedPrice = normalizedPaperLimitCreatePrice(intent);
    if (normalizedPrice === null) {
      throw new Error(
        "valid volume, authoritative tickSize and valid price are required",
      );
    }
    const clientActionId = dependencies.createClientActionId();
    const request = buildRequest(intent, normalizedPrice, clientActionId);
    const attempt: PaperLimitCreateAttempt = {
      intentId,
      clientActionId,
      promise: Promise.resolve({ certainty: "ambiguous" }),
    };
    attempt.promise = executePaperLimitCommand(request, {
      fetcher: dependencies.fetcher,
      applyPaperState: dependencies.applyPaperState,
    })
      .then(
        (value): PaperLimitCreateOutcome => ({
          certainty: "definitive",
          value,
        }),
      )
      .catch(
        (error: unknown): PaperLimitCreateOutcome => ({
          certainty: "ambiguous",
          error,
        }),
      )
      .then((outcome) => {
        if (
          outcome.certainty === "definitive" &&
          this.attempts.get(intentId) === attempt
        ) {
          this.attempts.delete(intentId);
        }
        return outcome;
      });
    this.attempts.set(intentId, attempt);
    return attempt;
  }

  releaseAfterReconciliation(intentId: string, clientActionId: string): void {
    const attempt = this.attempts.get(intentId);
    if (attempt?.clientActionId === clientActionId)
      this.attempts.delete(intentId);
  }
}

const DOM_ACTIVATION_ANTI_BOUNCE_MS = 300;

/** Adds one-at-a-time DOM intent ownership and accidental repeat suppression. */
export class DomLimitPlacementController {
  private readonly creates = new PaperLimitCreateController();
  private sequence = 0;
  private active: PaperLimitCreateAttempt | null = null;
  private recent: {
    attempt: PaperLimitCreateAttempt;
    startedAt: number;
  } | null = null;

  submit(
    intent: PaperLimitCreateIntent,
    dependencies: PaperLimitCreateDependencies,
    now = Date.now(),
  ): PaperLimitCreateAttempt {
    if (this.active) return this.active;
    if (
      this.recent &&
      now - this.recent.startedAt < DOM_ACTIVATION_ANTI_BOUNCE_MS
    )
      return this.recent.attempt;

    this.sequence += 1;
    const intentId = `dom-limit-intent-${this.sequence}`;
    const attempt = this.creates.submit(intentId, intent, dependencies);
    this.active = attempt;
    this.recent = { attempt, startedAt: now };
    void attempt.promise.then((outcome) => {
      if (outcome.certainty === "definitive" && this.active === attempt) {
        this.active = null;
      }
    });
    return attempt;
  }

  releaseAfterReconciliation(attempt: PaperLimitCreateAttempt): void {
    this.creates.releaseAfterReconciliation(
      attempt.intentId,
      attempt.clientActionId,
    );
    if (this.active === attempt) this.active = null;
    if (this.recent?.attempt === attempt) this.recent = null;
  }
}
