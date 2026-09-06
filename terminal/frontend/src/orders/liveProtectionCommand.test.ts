import { describe, expect, it, vi } from "vitest";
import { executeLiveProtection } from "./liveProtectionCommand";

const request = {
  client_action_id: "action-1",
  account_id: "bybit-main",
  session_generation: 7,
  symbol: "BTCUSDT",
  take_profit: "65000",
  stop_loss: "62000",
  tp_trigger_by: "MarkPrice" as const,
  sl_trigger_by: "MarkPrice" as const,
};

const response = {
  status: "accepted_pending",
  reason_code: "accepted_pending",
  command_id: "command-1",
  reconciliation_required: false,
};

describe("executeLiveProtection", () => {
  it("posts the complete protection state to the operation-specific endpoint", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(response)));

    await executeLiveProtection(
      "STOP",
      "AMEND",
      request,
      () => ({ accountId: "bybit-main", sessionGeneration: 7 }),
      fetcher,
    );

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, options] = fetcher.mock.calls[0];
    expect(url).toBe("/api/live/stop/amend");
    expect(JSON.parse(options!.body as string)).toEqual(request);
  });

  it("returns null when authority changed while the request was in flight", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(response)));

    const result = await executeLiveProtection(
      "TAKE",
      "DELETE",
      request,
      () => ({ accountId: "bybit-other", sessionGeneration: 8 }),
      fetcher,
    );

    expect(result).toBeNull();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/live/take/delete",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
