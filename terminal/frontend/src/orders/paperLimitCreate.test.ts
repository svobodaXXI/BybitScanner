import { describe, expect, it, vi } from "vitest";
import type {
  PaperLimitMutationResponse,
  PaperState,
} from "../contracts/trading";
import {
  DomLimitPlacementController,
  PaperLimitCreateController,
  type PaperLimitCreateIntent,
} from "./paperLimitCreate";

const paperState: PaperState = {
  ok: true,
  state_revision: 2,
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

const intent: PaperLimitCreateIntent = {
  symbol: "BTCUSDT",
  side: "Buy",
  volume: { unit: "usdt", amount: "250" },
  sizingReferencePrice: "64250",
  price: "62965.24",
  authoritativeTickSize: "0.5",
};

const completed = (clientActionId: string): PaperLimitMutationResponse => ({
  client_action_id: clientActionId,
  status: "completed",
  reason_code: "created",
  order_id: "paper-limit-1",
  paper_state: paperState,
});

const response = (value: PaperLimitMutationResponse) =>
  ({ json: vi.fn().mockResolvedValue(value) }) as unknown as Response;

describe("PaperLimitCreateController", () => {
  it("keeps one client_action_id and one transport for a repeated intent", async () => {
    let resolveResponse!: (value: Response) => void;
    const fetcher = vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveResponse = resolve;
      }),
    );
    const createClientActionId = vi.fn(() => "stable-action");
    const applyPaperState = vi.fn(() => true);
    const controller = new PaperLimitCreateController();
    const dependencies = {
      createClientActionId,
      applyPaperState,
      fetcher: fetcher as unknown as typeof fetch,
    };

    const first = controller.submit("intent-1", intent, dependencies);
    const repeated = controller.submit("intent-1", intent, dependencies);
    expect(repeated).toBe(first);
    expect(createClientActionId).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledOnce();

    resolveResponse(response(completed("stable-action")));
    await first.promise;
    expect(applyPaperState).toHaveBeenCalledWith(paperState);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({
      client_action_id: "stable-action",
      limit_price: "62965",
      volume: { unit: "usdt", amount: "250" },
    });
  });
});

describe("DomLimitPlacementController", () => {
  it("releases a completed placement and gives a later tap a new identity", async () => {
    const createClientActionId = vi
      .fn()
      .mockReturnValueOnce("dom-action-1")
      .mockReturnValueOnce("dom-action-2");
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response(completed("dom-action-1")))
      .mockResolvedValueOnce(response(completed("dom-action-2")));
    const controller = new DomLimitPlacementController();
    const dependencies = {
      createClientActionId,
      applyPaperState: vi.fn(() => true),
      fetcher: fetcher as unknown as typeof fetch,
    };

    const first = controller.submit(intent, dependencies, 1_000);
    const repeated = controller.submit(intent, dependencies, 1_299);
    expect(repeated).toBe(first);
    await first.promise;
    expect(createClientActionId).toHaveBeenCalledOnce();
    expect(fetcher).toHaveBeenCalledOnce();

    const next = controller.submit(intent, dependencies, 1_300);
    expect(next).not.toBe(first);
    await next.promise;
    expect(createClientActionId).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("fails closed on ambiguity until reconciliation releases the intent", async () => {
    const createClientActionId = vi
      .fn()
      .mockReturnValueOnce("ambiguous-action")
      .mockReturnValueOnce("after-reconciliation");
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce(response(completed("after-reconciliation")));
    const controller = new DomLimitPlacementController();
    const dependencies = {
      createClientActionId,
      applyPaperState: vi.fn(() => true),
      fetcher: fetcher as unknown as typeof fetch,
    };

    const first = controller.submit(intent, dependencies, 1_000);
    expect((await first.promise).certainty).toBe("ambiguous");
    expect(controller.submit(intent, dependencies, 2_000)).toBe(first);
    expect(createClientActionId).toHaveBeenCalledOnce();

    controller.releaseAfterReconciliation(first);
    const reconciled = controller.submit(intent, dependencies, 2_001);
    expect(reconciled).not.toBe(first);
    await reconciled.promise;
    expect(createClientActionId).toHaveBeenCalledTimes(2);
  });
});
