import { describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import {
  LiveLimitOrderMutationController,
  PaperLimitOrderMutationController,
  type PaperLimitOrderMutationDependencies,
} from "./limitOrderMutationSubmission";

function paperState(): PaperState {
  return {
    ok: true,
    state_revision: 1,
    account_id: "paper",
    symbol: "BTCUSDT",
    initial_deposit_usdt: "1000",
    equity_usdt: "1000",
    one_wv_usdt: "50",
    position_side: "Flat",
    position_quantity: "0",
    average_entry: null,
    engaged_notional_usdt: "0",
    engaged_wv: "0",
    active_limit_orders: [],
  };
}

describe("existing Limit mutation adapters", () => {
  it("PAPER amend uses one shared-owned attempt and applies the returned authoritative state", async () => {
    const applyPaperState = vi.fn(() => true);
    const fetcher = vi.fn().mockResolvedValue({
      json: async () => ({
        client_action_id: "paper-amend-1",
        status: "completed",
        reason_code: "ok",
        order_id: "order-1",
        paper_state: paperState(),
      }),
    });
    const runMutation = vi.fn(async (_key: string, operation: () => Promise<unknown>) => operation());
    const dependencies: PaperLimitOrderMutationDependencies = {
      createClientActionId: () => "paper-amend-1",
      applyPaperState,
      runMutation: runMutation as PaperLimitOrderMutationDependencies["runMutation"],
      refreshPaper: vi.fn(async () => undefined),
      fetcher: fetcher as unknown as typeof fetch,
    };
    const controller = new PaperLimitOrderMutationController();

    const first = controller.amend({ symbol: "BTCUSDT", orderId: "order-1", price: "49000" }, dependencies);
    const second = controller.amend({ symbol: "BTCUSDT", orderId: "order-1", price: "49000" }, dependencies);
    const result = await first.promise;

    expect(second).toBe(first);
    expect(runMutation).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({
      client_action_id: "paper-amend-1",
      symbol: "BTCUSDT",
      order_id: "order-1",
      limit_price: "49000",
    });
    expect(applyPaperState).toHaveBeenCalledTimes(1);
    expect(result.status).toBe("completed");
  });

  it("PAPER transport failure reconciles and releases ownership", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("network"));
    const refreshPaper = vi.fn(async () => undefined);
    const runMutation = vi.fn(async (_key: string, operation: () => Promise<unknown>) => operation());
    let action = 0;
    const dependencies: PaperLimitOrderMutationDependencies = {
      createClientActionId: () => `paper-cancel-${++action}`,
      applyPaperState: () => true,
      runMutation: runMutation as PaperLimitOrderMutationDependencies["runMutation"],
      refreshPaper,
      fetcher: fetcher as unknown as typeof fetch,
    };
    const controller = new PaperLimitOrderMutationController();

    const first = controller.cancel({ symbol: "BTCUSDT", orderId: "order-1" }, dependencies);
    await expect(first.promise).rejects.toThrow("network");
    const second = controller.cancel({ symbol: "BTCUSDT", orderId: "order-1" }, dependencies);
    await expect(second.promise).rejects.toThrow("network");

    expect(refreshPaper).toHaveBeenCalledTimes(2);
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(second.clientActionId).toBe("paper-cancel-2");
  });

  it("LIVE accepted amend refreshes authoritative projection before releasing ownership", async () => {
    const authority = { accountId: "bybit-main", sessionGeneration: 7 };
    const refreshActiveLive = vi.fn(async () => undefined);
    const fetcher = vi.fn().mockResolvedValue({
      json: async () => ({
        status: "accepted_pending",
        reason_code: "submitted",
        command_id: "cmd-1",
        reconciliation_required: false,
      }),
    });
    let action = 0;
    const dependencies = {
      currentAuthority: () => authority,
      createClientActionId: () => `live-amend-${++action}`,
      refreshActiveLive,
      fetcher: fetcher as unknown as typeof fetch,
    };
    const controller = new LiveLimitOrderMutationController();

    const first = controller.amend({ symbol: "BTCUSDT", orderId: "order-1", price: "49100" }, dependencies);
    const duplicate = controller.amend({ symbol: "BTCUSDT", orderId: "order-1", price: "49100" }, dependencies);
    await first.promise;
    const next = controller.amend({ symbol: "BTCUSDT", orderId: "order-1", price: "49200" }, dependencies);
    await next.promise;

    expect(duplicate).toBe(first);
    expect(first.clientActionId).toBe("live-amend-1");
    expect(next.clientActionId).toBe("live-amend-2");
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(refreshActiveLive).toHaveBeenCalledTimes(2);
  });

  it("LIVE unknown cancel remains latched and is not blindly redispatched", async () => {
    const authority = { accountId: "bybit-main", sessionGeneration: 7 };
    const fetcher = vi.fn().mockResolvedValue({
      json: async () => ({
        status: "unknown",
        reason_code: "transport_ambiguous",
        command_id: "cmd-1",
        reconciliation_required: true,
      }),
    });
    const dependencies = {
      currentAuthority: () => authority,
      createClientActionId: () => "stable-cancel",
      refreshActiveLive: vi.fn(async () => undefined),
      fetcher: fetcher as unknown as typeof fetch,
    };
    const controller = new LiveLimitOrderMutationController();

    const first = controller.cancel({ symbol: "BTCUSDT", orderId: "order-1" }, dependencies);
    await first.promise;
    const second = controller.cancel({ symbol: "BTCUSDT", orderId: "order-1" }, dependencies);

    expect(second).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(dependencies.refreshActiveLive).not.toHaveBeenCalled();
  });

  it("LIVE transport ambiguity remains latched until authority invalidation clears ownership", async () => {
    const authority = { accountId: "bybit-main", sessionGeneration: 7 };
    const fetcher = vi.fn().mockRejectedValue(new Error("timeout"));
    let action = 0;
    const dependencies = {
      currentAuthority: () => authority,
      createClientActionId: () => `live-cancel-${++action}`,
      refreshActiveLive: vi.fn(async () => undefined),
      fetcher: fetcher as unknown as typeof fetch,
    };
    const controller = new LiveLimitOrderMutationController();

    const first = controller.cancel({ symbol: "BTCUSDT", orderId: "order-1" }, dependencies);
    await expect(first.promise).rejects.toThrow("timeout");
    const duplicate = controller.cancel({ symbol: "BTCUSDT", orderId: "order-1" }, dependencies);
    expect(duplicate).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);

    controller.clear();
    const afterInvalidation = controller.cancel({ symbol: "BTCUSDT", orderId: "order-1" }, dependencies);
    await expect(afterInvalidation.promise).rejects.toThrow("timeout");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("LIVE stale authority fails before transport and does not become a latched attempt", () => {
    const fetcher = vi.fn();
    const dependencies = {
      currentAuthority: () => null,
      createClientActionId: () => "should-not-be-used",
      refreshActiveLive: vi.fn(async () => undefined),
      fetcher: fetcher as unknown as typeof fetch,
    };
    const controller = new LiveLimitOrderMutationController();

    expect(() => controller.amend(
      { symbol: "BTCUSDT", orderId: "order-1", price: "49000" },
      dependencies,
    )).toThrow("stale_live_authority");
    expect(fetcher).not.toHaveBeenCalled();
  });
});
