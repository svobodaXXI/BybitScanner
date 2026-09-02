import { describe, expect, it, vi } from "vitest";
import {
  executeLiveLimitAmend,
  executeLiveLimitCancel,
  executeLiveLimitCreate,
  liveLimitCreateRequest,
  projectLiveLimitOrders,
} from "./liveLimitCommand";

describe("LIVE Limit transport", () => {
  it("stamps captured authority, uses the LIVE endpoint and rejects stale responses", async () => {
    const request = liveLimitCreateRequest({
      authority: { accountId: "bybit-main", sessionGeneration: 7 },
      clientActionId: "stable-action", symbol: "BTCUSDT", side: "Buy",
      volume: { unit: "usdt", amount: "10" }, sizingReferencePrice: "50000",
      limitPrice: "49000",
    });
    const fetcher = vi.fn().mockResolvedValue({ json: async () => ({
      status: "accepted_pending", reason_code: "submitted", command_id: "cmd-1",
      reconciliation_required: true,
    }) });
    const result = await executeLiveLimitCreate(request, () => ({
      accountId: "paper", sessionGeneration: 8,
    }), fetcher as unknown as typeof fetch);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("/api/live/limit");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({
      client_action_id: "stable-action", account_id: "bybit-main", session_generation: 7,
    });
    expect(result).toBeNull();
  });

  it("projects only valid current-symbol LIVE Limit orders", () => {
    expect(projectLiveLimitOrders([
      { symbol: "BTCUSDT", order_id: "one", side: "Buy", order_type: "Limit", price: "49000", quantity: "0.01" },
      { symbol: "ETHUSDT", order_id: "two", side: "Sell", order_type: "Limit", price: "4000", quantity: "1" },
      { symbol: "BTCUSDT", order_id: "three", side: "Buy", order_type: "Market", price: "0", quantity: "0.01" },
    ], "BTCUSDT")).toEqual([expect.objectContaining({ order_id: "one", side: "Buy", price: "49000" })]);
  });

  it("uses separate amend and cancel routes with captured authority", async () => {
    const authority = { accountId: "bybit-main", sessionGeneration: 7 };
    const fetcher = vi.fn().mockResolvedValue({ json: async () => ({
      status: "accepted_pending", reason_code: "submitted", command_id: "cmd-1",
      reconciliation_required: true,
    }) });
    await executeLiveLimitAmend({
      client_action_id: "amend-action", account_id: authority.accountId,
      session_generation: authority.sessionGeneration, symbol: "BTCUSDT",
      order_id: "order-1", limit_price: "49100",
    }, () => authority, fetcher as unknown as typeof fetch);
    await executeLiveLimitCancel({
      client_action_id: "cancel-action", account_id: authority.accountId,
      session_generation: authority.sessionGeneration, symbol: "BTCUSDT", order_id: "order-1",
    }, () => authority, fetcher as unknown as typeof fetch);
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
      "/api/live/limit/amend", "/api/live/limit/cancel",
    ]);
  });
});
