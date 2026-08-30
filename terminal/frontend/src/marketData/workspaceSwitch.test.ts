import { describe, expect, it, vi } from "vitest";
import { requestWorkspaceActivation } from "./workspaceSwitch";

describe("transactional Workspace activation", () => {
  it("returns authoritative symbol and generation only from a valid ACK", async () => {
    const fetcher = vi.fn(async () => ({
      ok: true,
      json: async () => ({ ok: true, symbol: "ETHUSDT", generation: 8 }),
    })) as unknown as typeof fetch;
    await expect(requestWorkspaceActivation("ethusdt", "/switch", fetcher)).resolves.toEqual({
      ok: true, symbol: "ETHUSDT", generation: 8,
    });
  });

  it("preserves the backend structured semantic failure", async () => {
    const workspace_error = {
      code: "candidate_not_ready", stage: "candidate_readiness",
      requested_symbol: "ETHUSDT", active_symbol: "BTCUSDT",
      retryable: true, request_id: "switch-1", message: "Candidate is not ready",
    };
    const fetcher = vi.fn(async () => ({
      ok: false, json: async () => ({ ok: false, workspace_error }),
    })) as unknown as typeof fetch;
    await expect(requestWorkspaceActivation("ETHUSDT", "/switch", fetcher)).resolves.toEqual({
      ok: false, error: workspace_error,
    });
  });

  it("fails closed on a missing or mismatched generation ACK", async () => {
    for (const payload of [
      { ok: true, symbol: "ETHUSDT" },
      { ok: true, symbol: "BTCUSDT", generation: 8 },
    ]) {
      const fetcher = vi.fn(async () => ({
        ok: true, json: async () => payload,
      })) as unknown as typeof fetch;
      const result = await requestWorkspaceActivation("ETHUSDT", "/switch", fetcher);
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.error.stage).toBe("workspace_activation_ack");
    }
  });
});
