import { describe, expect, it, vi } from "vitest";
import type { PaperLimitMutationResponse, PaperState } from "../contracts/trading";
import { createLimitDraft, type LimitDraftAction } from "./limitDraft";
import { PaperLimitDraftSubmitController } from "./limitDraftSubmission";

const draft = () =>
  createLimitDraft({
    draftId: "draft-1",
    symbol: "BTCUSDT",
    side: "Buy",
    origin: "limits-popup",
    volume: { unit: "working_volume", amount: "1" },
    sizingReferencePrice: "64250",
    price: "62965",
    authoritativeTickSize: "0.5",
  });

const paperState: PaperState = {
  ok: true,
  state_revision: 1,
  account_id: "paper",
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

const response = (result: PaperLimitMutationResponse) =>
  ({ json: vi.fn().mockResolvedValue(result) }) as unknown as Response;

describe("PaperLimitDraftSubmitController", () => {
  it("deduplicates one successful attempt, clears once, and refreshes authority", async () => {
    const dispatch = vi.fn<(action: LimitDraftAction) => void>();
    const applyPaperState = vi.fn(() => true);
    let resolveResponse!: (value: Response) => void;
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    const fetcher = vi.fn().mockReturnValue(pendingResponse);
    const completedResponse = response({
      client_action_id: "action-1",
      status: "completed",
      reason_code: "created",
      order_id: "paper-limit-1",
      paper_state: paperState,
    });
    const createClientActionId = vi.fn(() => "action-1");
    const controller = new PaperLimitDraftSubmitController();
    const dependencies = {
      dispatch,
      applyPaperState,
      createClientActionId,
      fetcher: fetcher as unknown as typeof fetch,
    };

    const first = controller.submit(draft(), dependencies);
    const repeated = controller.submit(draft(), dependencies);

    expect(repeated).toBe(first);
    expect(repeated.promise).toBe(first.promise);
    await Promise.resolve();
    expect(applyPaperState).not.toHaveBeenCalled();
    expect(dispatch.mock.calls.some(([action]) => action.type === "dismiss")).toBe(false);
    resolveResponse(completedResponse);
    await first.promise;
    expect(applyPaperState).toHaveBeenCalledWith(paperState);

    expect(createClientActionId).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({
      client_action_id: "action-1",
      symbol: "BTCUSDT",
      limit_price: "62965",
      time_in_force: "GTC",
    });
    expect(dispatch.mock.calls.filter(([action]) => action.type === "dismiss")).toHaveLength(1);
  });

  it("keeps a rejected draft and preserves an ambiguous attempt lock", async () => {
    const rejectedDispatch = vi.fn<(action: LimitDraftAction) => void>();
    const rejected = new PaperLimitDraftSubmitController();
    const rejectedAttempt = rejected.submit(draft(), {
      dispatch: rejectedDispatch,
      applyPaperState: vi.fn(() => true),
      createClientActionId: () => "rejected-action",
      fetcher: vi.fn().mockResolvedValue(response({
        client_action_id: "rejected-action",
        status: "blocked",
        reason_code: "blocked",
        order_id: null,
        paper_state: paperState,
      })) as unknown as typeof fetch,
    });
    await rejectedAttempt.promise;
    await vi.waitFor(() =>
      expect(rejectedDispatch).toHaveBeenCalledWith({
        type: "mark-rejected",
        clientActionId: "rejected-action",
        reason: "blocked",
        draftId: "draft-1",
      }),
    );
    expect(rejectedDispatch).not.toHaveBeenCalledWith({ type: "dismiss" });

    const ambiguousDispatch = vi.fn<(action: LimitDraftAction) => void>();
    const createId = vi.fn(() => "ambiguous-action");
    const ambiguous = new PaperLimitDraftSubmitController();
    const dependencies = {
      dispatch: ambiguousDispatch,
      applyPaperState: vi.fn(() => true),
      createClientActionId: createId,
      fetcher: vi.fn().mockRejectedValue(new Error("network")) as unknown as typeof fetch,
    };
    const first = ambiguous.submit(draft(), dependencies);
    await first.promise;
    const repeated = ambiguous.submit(draft(), dependencies);

    expect(repeated).toBe(first);
    expect(createId).toHaveBeenCalledTimes(1);
    await vi.waitFor(() =>
      expect(ambiguousDispatch).toHaveBeenCalledWith({
        type: "mark-ambiguous",
        clientActionId: "ambiguous-action",
        draftId: "draft-1",
      }),
    );
  });
});
