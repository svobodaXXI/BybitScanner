import { describe, expect, it, vi } from "vitest";
import { executeLiveFullClose } from "./liveFullCloseCommand";

const request = {
  client_action_id: "action-1",
  account_id: "bybit-main",
  session_generation: 7,
  symbol: "BTCUSDT",
};

describe("executeLiveFullClose", () => {
  it("posts the authority-fenced FULL_CLOSE request", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({
      status: "accepted_pending", reason_code: "accepted_pending", command_id: "cmd-1",
      reconciliation_required: false,
    })));
    const result = await executeLiveFullClose(
      request,
      () => ({ accountId: "bybit-main", sessionGeneration: 7 }),
      fetcher,
    );
    expect(result?.status).toBe("accepted_pending");
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/live/full-close");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual(request);
  });

  it("drops a response after authority changes", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({
      status: "accepted_pending", reason_code: "accepted_pending", command_id: "cmd-1",
      reconciliation_required: false,
    })));
    const result = await executeLiveFullClose(
      request,
      () => ({ accountId: "other", sessionGeneration: 8 }),
      fetcher,
    );
    expect(result).toBeNull();
  });
});
