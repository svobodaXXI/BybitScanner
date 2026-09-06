import { describe, expect, it, vi } from "vitest";
import { createLimitDraft, type LimitDraftAction } from "./limitDraft";
import { LiveLimitDraftSubmitController } from "./liveLimitDraftSubmission";

const draft = () => createLimitDraft({
  draftId: "live-draft-1",
  symbol: "ONGUSDT",
  side: "Buy",
  origin: "chart-fast",
  volume: { unit: "usdt", amount: "5" },
  sizingReferencePrice: "0.1005",
  price: "0.09849",
  authoritativeTickSize: "0.00001",
});

const authority = () => ({ accountId: "bybit-main", sessionGeneration: 8 });

describe("LiveLimitDraftSubmitController", () => {
  it("uses the shared completed lifecycle, refreshes once, and deduplicates dispatch", async () => {
    const dispatch = vi.fn<(action: LimitDraftAction) => void>();
    const refreshActiveLive = vi.fn(async () => {});
    const fetcher = vi.fn(async () => ({
      json: async () => ({
        status: "accepted_pending",
        reason_code: "accepted_pending",
        command_id: "command-1",
        reconciliation_required: true,
      }),
    })) as unknown as typeof fetch;
    const controller = new LiveLimitDraftSubmitController();
    const dependencies = {
      dispatch,
      currentAuthority: authority,
      createClientActionId: () => "live-action-1",
      refreshActiveLive,
      fetcher,
    };

    const first = controller.submit(draft(), dependencies);
    const repeated = controller.submit(draft(), dependencies);

    expect(repeated).toBe(first);
    await first.promise;

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({
      type: "start-submitting",
      clientActionId: "live-action-1",
      draftId: "live-draft-1",
    });
    expect(dispatch).toHaveBeenCalledWith({ type: "dismiss", draftId: "live-draft-1" });
    expect(refreshActiveLive).toHaveBeenCalledTimes(1);
  });

  it.each(["unknown", "network"] as const)("keeps %s ambiguous and latched without retry", async (mode) => {
    const dispatch = vi.fn<(action: LimitDraftAction) => void>();
    const fetcher = vi.fn(async () => {
      if (mode === "network") throw new Error("connection lost");
      return {
        json: async () => ({
          status: "unknown",
          reason_code: "unknown",
          command_id: "command-unknown",
          reconciliation_required: true,
        }),
      };
    }) as unknown as typeof fetch;
    const controller = new LiveLimitDraftSubmitController();
    const dependencies = {
      dispatch,
      currentAuthority: authority,
      createClientActionId: () => "live-action-ambiguous",
      refreshActiveLive: vi.fn(async () => {}),
      fetcher,
    };

    const first = controller.submit(draft(), dependencies);
    await first.promise;
    const repeated = controller.submit(draft(), dependencies);

    expect(repeated).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({
      type: "mark-ambiguous",
      clientActionId: "live-action-ambiguous",
      draftId: "live-draft-1",
    });
  });
});
