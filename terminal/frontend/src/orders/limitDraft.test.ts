import { describe, expect, it, vi } from "vitest";
import {
  canConfirmLimitDraft,
  createLimitDraft,
  EMPTY_LIMIT_DRAFT_STATE,
  type LimitDraftOrigin,
  LimitDraftSubmitLatch,
  limitDraftReducer,
  normalizeLimitDraftPrice,
} from "./limitDraft";

function draft(
  origin: LimitDraftOrigin = "limits-popup",
  tickSize: string | null = "0.05",
) {
  return createLimitDraft({
    draftId: "draft-1",
    symbol: "ONGUSDT",
    side: "Buy",
    origin,
    volume: { unit: "usdt", amount: "100" },
    sizingReferencePrice: "10.12",
    price: "10.12",
    authoritativeTickSize: tickSize,
  });
}

describe("Limit Draft foundation", () => {
  it("normalizes BUY down and SELL up without floating-point drift", () => {
    expect(normalizeLimitDraftPrice("10.12", "0.05", "Buy")).toBe("10.1");
    expect(normalizeLimitDraftPrice("10.12", "0.05", "Sell")).toBe("10.15");
    expect(normalizeLimitDraftPrice("0.094567", "0.00001", "Buy")).toBe(
      "0.09456",
    );
    expect(normalizeLimitDraftPrice("0.094567", "0.00001", "Sell")).toBe(
      "0.09457",
    );
  });

  it("uses one model for every future origin and still owns only one draft", () => {
    let state = EMPTY_LIMIT_DRAFT_STATE;
    for (const origin of ["limits-popup", "chart-fast", "dom-fast"] as const) {
      state = limitDraftReducer(state, { type: "begin", draft: draft(origin) });
      expect(state.draft?.origin).toBe(origin);
    }
    expect(state.drafts).toHaveLength(1);
  });

  it("blocks confirmation without authoritative tickSize", () => {
    const missingTick = draft("limits-popup", null);
    expect(canConfirmLimitDraft(missingTick)).toBe(false);
    expect(
      limitDraftReducer(
        { draft: missingTick },
        { type: "start-submitting", clientActionId: "action-1" },
      ),
    ).toEqual({ draft: missingTick });
  });

  it("preserves the typed decimal until submission normalization", () => {
    const editing = limitDraftReducer(
      { draft: draft(), drafts: [draft()] },
      { type: "update-price", price: "10.1230" },
    );

    expect(editing.draft?.price).toBe("10.1230");
    expect(normalizeLimitDraftPrice(editing.draft?.price ?? "", "0.05", "Buy"))
      .toBe("10.1");
  });

  it("keeps the submission identity stable in reducer transitions", () => {
    const submitting = limitDraftReducer(
      { draft: draft() },
      { type: "start-submitting", clientActionId: "action-1" },
    );
    const repeated = limitDraftReducer(submitting, {
      type: "start-submitting",
      clientActionId: "action-2",
    });
    const ambiguous = limitDraftReducer(repeated, {
      type: "mark-ambiguous",
      clientActionId: "action-1",
    });
    expect(repeated).toBe(submitting);
    expect(ambiguous.draft).toMatchObject({
      status: "ambiguous",
      clientActionId: "action-1",
    });
  });

  it("reuses one action ID and the exact same promise while submitting", async () => {
    let resolveSubmit!: (value: {
      certainty: "definitive";
      value: string;
    }) => void;
    const submitter = vi.fn(
      () =>
        new Promise<{ certainty: "definitive"; value: string }>((resolve) => {
          resolveSubmit = resolve;
        }),
    );
    const createId = vi.fn(() => "action-1");
    const latch = new LimitDraftSubmitLatch<string>();

    const first = latch.submit(draft(), createId, submitter);
    const second = latch.submit(draft(), createId, submitter);

    expect(second).toBe(first);
    expect(second.promise).toBe(first.promise);
    expect(first.clientActionId).toBe("action-1");
    expect(createId).toHaveBeenCalledTimes(1);
    await Promise.resolve();
    expect(submitter).toHaveBeenCalledTimes(1);
    resolveSubmit({ certainty: "definitive", value: "created" });
    await expect(first.promise).resolves.toEqual({
      certainty: "definitive",
      value: "created",
    });
  });

  it("keeps an ambiguous attempt latched until explicit reconciliation", async () => {
    const createId = vi
      .fn<() => string>()
      .mockReturnValueOnce("action-1")
      .mockReturnValueOnce("action-2");
    const submitter = vi.fn().mockResolvedValue({ certainty: "ambiguous" });
    const latch = new LimitDraftSubmitLatch<string>();

    const first = latch.submit(draft(), createId, submitter);
    await expect(first.promise).resolves.toEqual({ certainty: "ambiguous" });
    const repeated = latch.submit(draft(), createId, submitter);

    expect(repeated).toBe(first);
    expect(repeated.clientActionId).toBe("action-1");
    expect(createId).toHaveBeenCalledTimes(1);
    expect(submitter).toHaveBeenCalledTimes(1);

    latch.releaseAfterReconciliation("draft-1", "action-1");
    const reconciledRetry = latch.submit(draft(), createId, submitter);
    expect(reconciledRetry.clientActionId).toBe("action-2");
  });
});
