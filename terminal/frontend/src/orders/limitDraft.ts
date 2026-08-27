import type { MarketSide, VolumeRequest } from "../contracts/trading";

export const LIMIT_DRAFT_ORIGINS = [
  "limits-popup",
  "chart-fast",
  "dom-fast",
] as const;

export type LimitDraftOrigin = (typeof LIMIT_DRAFT_ORIGINS)[number];
export type LimitDraftStatus =
  | "draft"
  | "editing"
  | "submitting"
  | "ambiguous"
  | "rejected";

export type LimitDraft = {
  draftId: string;
  symbol: string;
  side: MarketSide;
  origin: LimitDraftOrigin;
  volume: VolumeRequest;
  sizingReferencePrice: string;
  price: string;
  authoritativeTickSize: string | null;
  status: LimitDraftStatus;
  clientActionId: string | null;
  rejectionReason: string | null;
};

export type LimitDraftState = {
  draft: LimitDraft | null;
};

export type LimitDraftAction =
  | { type: "begin"; draft: LimitDraft }
  | { type: "update-price"; price: string }
  | { type: "start-submitting"; clientActionId: string }
  | { type: "mark-ambiguous"; clientActionId: string }
  | { type: "mark-rejected"; clientActionId: string; reason: string }
  | { type: "dismiss" };

export const EMPTY_LIMIT_DRAFT_STATE: LimitDraftState = { draft: null };

type ParsedDecimal = {
  units: bigint;
  scale: number;
};

function parsePositiveDecimal(value: string): ParsedDecimal | null {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return null;
  const fraction = match[2] ?? "";
  const units = BigInt(`${match[1]}${fraction}`);
  return units > 0n ? { units, scale: fraction.length } : null;
}

function alignUnits(decimal: ParsedDecimal, scale: number): bigint {
  return decimal.units * 10n ** BigInt(scale - decimal.scale);
}

function formatUnits(units: bigint, scale: number): string {
  if (scale === 0) return units.toString();
  const padded = units.toString().padStart(scale + 1, "0");
  const integer = padded.slice(0, -scale);
  const fraction = padded.slice(-scale).replace(/0+$/, "");
  return fraction ? `${integer}.${fraction}` : integer;
}

/**
 * Presentation-side normalization only. The backend remains authoritative and
 * repeats normalization during admission.
 */
export function normalizeLimitDraftPrice(
  price: string,
  authoritativeTickSize: string | null,
  side: MarketSide,
): string | null {
  if (authoritativeTickSize === null) return null;
  const parsedPrice = parsePositiveDecimal(price);
  const parsedTick = parsePositiveDecimal(authoritativeTickSize);
  if (!parsedPrice || !parsedTick) return null;

  const scale = Math.max(parsedPrice.scale, parsedTick.scale);
  const priceUnits = alignUnits(parsedPrice, scale);
  const tickUnits = alignUnits(parsedTick, scale);
  const quotient = priceUnits / tickUnits;
  const remainder = priceUnits % tickUnits;
  const tickCount =
    side === "Buy" || remainder === 0n ? quotient : quotient + 1n;
  const normalizedUnits = tickCount * tickUnits;
  return normalizedUnits > 0n ? formatUnits(normalizedUnits, scale) : null;
}

export function createLimitDraft(input: {
  draftId: string;
  symbol: string;
  side: MarketSide;
  origin: LimitDraftOrigin;
  volume: VolumeRequest;
  sizingReferencePrice: string;
  price: string;
  authoritativeTickSize: string | null;
}): LimitDraft {
  return {
    ...input,
    price:
      normalizeLimitDraftPrice(
        input.price,
        input.authoritativeTickSize,
        input.side,
      ) ?? input.price,
    status: "draft",
    clientActionId: null,
    rejectionReason: null,
  };
}

export function normalizedLimitDraftPrice(draft: LimitDraft): string | null {
  return normalizeLimitDraftPrice(
    draft.price,
    draft.authoritativeTickSize,
    draft.side,
  );
}

export function canConfirmLimitDraft(draft: LimitDraft): boolean {
  return (
    draft.status !== "submitting" &&
    draft.status !== "ambiguous" &&
    normalizedLimitDraftPrice(draft) !== null
  );
}

export function limitDraftReducer(
  state: LimitDraftState,
  action: LimitDraftAction,
): LimitDraftState {
  if (action.type === "begin") return { draft: action.draft };
  if (action.type === "dismiss") return EMPTY_LIMIT_DRAFT_STATE;
  const draft = state.draft;
  if (!draft) return state;

  if (action.type === "update-price") {
    if (draft.status === "submitting" || draft.status === "ambiguous") {
      return state;
    }
    return {
      draft: {
        ...draft,
        price:
          normalizeLimitDraftPrice(
            action.price,
            draft.authoritativeTickSize,
            draft.side,
          ) ?? action.price,
        status: "editing",
        clientActionId: null,
        rejectionReason: null,
      },
    };
  }

  if (action.type === "start-submitting") {
    if (!canConfirmLimitDraft(draft)) return state;
    return {
      draft: {
        ...draft,
        price: normalizedLimitDraftPrice(draft) ?? draft.price,
        status: "submitting",
        clientActionId: action.clientActionId,
        rejectionReason: null,
      },
    };
  }

  if (
    draft.clientActionId === null ||
    draft.clientActionId !== action.clientActionId
  ) {
    return state;
  }

  if (action.type === "mark-ambiguous") {
    return { draft: { ...draft, status: "ambiguous" } };
  }

  return {
    draft: {
      ...draft,
      status: "rejected",
      clientActionId: null,
      rejectionReason: action.reason,
    },
  };
}

export type LimitSubmitOutcome<T> =
  | { certainty: "definitive"; value: T }
  | { certainty: "ambiguous"; error?: unknown };

export type LimitSubmitAttempt<T> = {
  draftId: string;
  clientActionId: string;
  promise: Promise<LimitSubmitOutcome<T>>;
};

/**
 * Owns one physical submission attempt. Ambiguous attempts remain latched until
 * an external reconciliation step explicitly releases the matching identity.
 */
export class LimitDraftSubmitLatch<T> {
  private attempt: LimitSubmitAttempt<T> | null = null;

  submit(
    draft: LimitDraft,
    createClientActionId: () => string,
    submitter: (draft: LimitDraft) => Promise<LimitSubmitOutcome<T>>,
  ): LimitSubmitAttempt<T> {
    if (this.attempt) {
      if (this.attempt.draftId !== draft.draftId) {
        throw new Error("another Limit draft submission is already latched");
      }
      return this.attempt;
    }

    const normalizedPrice = normalizedLimitDraftPrice(draft);
    if (normalizedPrice === null) {
      throw new Error("authoritative tickSize and valid price are required");
    }

    const clientActionId = draft.clientActionId ?? createClientActionId();
    const submittingDraft: LimitDraft = {
      ...draft,
      price: normalizedPrice,
      status: "submitting",
      clientActionId,
      rejectionReason: null,
    };
    const attempt: LimitSubmitAttempt<T> = {
      draftId: draft.draftId,
      clientActionId,
      promise: Promise.resolve({ certainty: "ambiguous" }),
    };
    attempt.promise = Promise.resolve()
      .then(() => submitter(submittingDraft))
      .then((outcome) => {
        if (outcome.certainty === "definitive" && this.attempt === attempt) {
          this.attempt = null;
        }
        return outcome;
      })
      .catch((error: unknown) => ({ certainty: "ambiguous", error }));
    this.attempt = attempt;
    return attempt;
  }

  releaseAfterReconciliation(draftId: string, clientActionId: string): void {
    if (
      this.attempt?.draftId === draftId &&
      this.attempt.clientActionId === clientActionId
    ) {
      this.attempt = null;
    }
  }
}
