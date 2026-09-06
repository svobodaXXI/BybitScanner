import { describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { createLimitDraft, type LimitDraftAction } from "./limitDraft";
import { PaperLimitDraftSubmitController } from "./limitDraftSubmission";
import {
  PaperLimitOrderMutationController,
  type PaperLimitOrderMutationDependencies,
} from "./limitOrderMutationSubmission";

const PAPER_STATE: PaperState = {
  ok: true,
  state_revision: 2,
  account_id: "paper-old",
  symbol: "BTCUSDT",
  initial_deposit_usdt: "5000",
  equity_usdt: "5000",
  one_wv_usdt: "250",
  position_side: "Flat",
  position_quantity: "0",
  average_entry: null,
  engaged_notional_usdt: "0",
  engaged_wv: "0.0",
  active_limit_orders: [],
};

const completedResponse = (clientActionId: string) => ({
  json: async () => ({
    client_action_id: clientActionId,
    status: "completed",
    reason_code: "ok",
    order_id: "order-1",
    paper_state: PAPER_STATE,
  }),
});

describe("PAPER Limit authoritative state fencing", () => {
  it("keeps CREATE ambiguous when completed state is rejected by the current PAPER session", async () => {
    const dispatch = vi.fn<(action: LimitDraftAction) => void>();
    const fetcher = vi.fn().mockResolvedValue(completedResponse("create-1"));
    const createClientActionId = vi.fn(() => "create-1");
    const controller = new PaperLimitDraftSubmitController();
    const draft = createLimitDraft({
      draftId: "draft-stale",
      symbol: "BTCUSDT",
      side: "Buy",
      origin: "limits-popup",
      volume: { unit: "working_volume", amount: "1" },
      sizingReferencePrice: "50000",
      price: "49000",
      authoritativeTickSize: "0.5",
    });
    const dependencies = {
      dispatch,
      createClientActionId,
      applyPaperState: vi.fn(() => false),
      fetcher: fetcher as unknown as typeof fetch,
    };

    const first = controller.submit(draft, dependencies);
    await first.promise;
    const repeated = controller.submit(draft, dependencies);

    expect(repeated).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith({
      type: "mark-ambiguous",
      clientActionId: "create-1",
      draftId: "draft-stale",
    });
    expect(dispatch).not.toHaveBeenCalledWith({ type: "dismiss", draftId: "draft-stale" });
  });

  it.each([
    ["amend", "paper_limit_amend_authoritative_state_rejected"],
    ["cancel", "paper_limit_cancel_authoritative_state_rejected"],
  ] as const)("fails closed and refreshes when %s completed state is rejected", async (kind, expectedError) => {
    const refreshPaper = vi.fn(async () => undefined);
    const fetcher = vi.fn().mockResolvedValue(completedResponse(`${kind}-1`));
    const runMutation = vi.fn(async (_key: string, operation: () => Promise<unknown>) => operation());
    const dependencies: PaperLimitOrderMutationDependencies = {
      createClientActionId: () => `${kind}-1`,
      applyPaperState: () => false,
      runMutation: runMutation as PaperLimitOrderMutationDependencies["runMutation"],
      refreshPaper,
      fetcher: fetcher as unknown as typeof fetch,
    };
    const controller = new PaperLimitOrderMutationController();

    const attempt = kind === "amend"
      ? controller.amend({ symbol: "BTCUSDT", orderId: "order-1", price: "49100" }, dependencies)
      : controller.cancel({ symbol: "BTCUSDT", orderId: "order-1" }, dependencies);

    await expect(attempt.promise).rejects.toThrow(expectedError);
    expect(refreshPaper).toHaveBeenCalledTimes(1);
  });
});
