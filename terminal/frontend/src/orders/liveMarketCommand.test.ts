import { describe, expect, it, vi } from "vitest";
import { createLiveMarketAction, executeLiveMarketCommand } from "./liveMarketCommand";

describe("LIVE Market command", () => {
  it("captures account/session and keeps one stable client action id", () => {
    const action = createLiveMarketAction({
      accountId: "bybit-main", sessionGeneration: 7, symbol: "BTCUSDT",
      side: "Buy", amount: "10", sizingReferencePrice: "50000",
      idFactory: () => "stable-action",
    });
    expect(action.client_action_id).toBe("stable-action");
    expect(action.account_id).toBe("bybit-main");
    expect(action.session_generation).toBe(7);
  });

  it("uses the separate endpoint and ignores a stale response after switch", async () => {
    const request = createLiveMarketAction({
      accountId: "bybit-main", sessionGeneration: 7, symbol: "BTCUSDT",
      side: "Sell", amount: "10", sizingReferencePrice: "50000",
      idFactory: () => "stable-action",
    });
    const fetcher = vi.fn().mockResolvedValue({ json: async () => ({
      status: "unknown", reason_code: "unknown_reconciling",
      command_id: "cmd-1", order_link_id: "tw-1", reconciliation_required: true,
    }) });
    const result = await executeLiveMarketCommand(request, {
      fetcher: fetcher as unknown as typeof fetch,
      currentAuthority: () => ({ accountId: "paper", sessionGeneration: 8 }),
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("/api/live/market");
    expect(result).toBeNull();
  });

  it("clears retained ownership when account/session authority changes", async () => {
    const first = createLiveMarketAction({
      accountId: "bybit-main-a", sessionGeneration: 10, symbol: "BTCUSDT",
      side: "Buy", amount: "10", sizingReferencePrice: "50000",
      idFactory: () => "reused-action-id",
    });
    const second = createLiveMarketAction({
      accountId: "bybit-main-b", sessionGeneration: 11, symbol: "BTCUSDT",
      side: "Buy", amount: "10", sizingReferencePrice: "50000",
      idFactory: () => "reused-action-id",
    });
    const fetcher = vi.fn()
      .mockResolvedValueOnce({ json: async () => ({
        status: "unknown", reason_code: "unknown_reconciling",
        command_id: "cmd-a", order_link_id: "tw-a", reconciliation_required: true,
      }) })
      .mockResolvedValueOnce({ json: async () => ({
        status: "completed", reason_code: "OK",
        command_id: "cmd-b", order_link_id: "tw-b", reconciliation_required: false,
      }) });

    await executeLiveMarketCommand(first, {
      fetcher: fetcher as unknown as typeof fetch,
      currentAuthority: () => ({ accountId: "bybit-main-a", sessionGeneration: 10 }),
    });
    const result = await executeLiveMarketCommand(second, {
      fetcher: fetcher as unknown as typeof fetch,
      currentAuthority: () => ({ accountId: "bybit-main-b", sessionGeneration: 11 }),
    });

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(result?.status).toBe("completed");
  });
});
