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
});
