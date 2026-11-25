import { describe, expect, it, vi } from "vitest";
import { requestWorkspaceActivation, matchesNavigationSnapshot, navigationTimingText, type WorkspaceNavigationTiming } from "./workspaceSwitch";
import type { MarketDataSnapshot } from "../contracts/marketData";

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

describe("MAIN position navigation timing", () => {
  const timing: WorkspaceNavigationTiming = {
    symbol: "ETHUSDT", interval: "1", startedAt: 100, ack: { generation: 8, at: 1200 },
  };
  const snapshot: MarketDataSnapshot = {
    source: "LIVE_NORMALIZED",
    book: { symbol: "ETHUSDT", bids: [], asks: [], health: "READY", receivedAt: "", availableDepth: 0 },
    workspace: { symbol: "ETHUSDT", generation: 8, interval: "1", streamId: "stream", eventSequence: 1, state: "READY" },
    candles: [{ time: "2026-11-25T00:00:00Z", open: 1, high: 1, low: 1, close: 1 }],
    tickSize: 0.1, trades: [], ownOrders: [],
  };
  it("does not measure old-generation, wrong-interval or empty snapshots", () => {
    expect(matchesNavigationSnapshot(timing, snapshot)).toBe(true);
    expect(matchesNavigationSnapshot(timing, { ...snapshot, workspace: { ...snapshot.workspace!, generation: 7 } })).toBe(false);
    expect(matchesNavigationSnapshot(timing, { ...snapshot, workspace: { ...snapshot.workspace!, interval: "5" } })).toBe(false);
    expect(matchesNavigationSnapshot(timing, { ...snapshot, candles: [] })).toBe(false);
    expect(matchesNavigationSnapshot({ ...timing, ack: undefined }, snapshot)).toBe(false);
  });
  it("reports stages separately without equating ACK and chart readiness", () => {
    expect(navigationTimingText({ ...timing, ack: undefined })).toContain("ожидание ACK");
    expect(navigationTimingText(timing)).toContain("ACK 1100 мс · ожидание снимка");
    expect(navigationTimingText({ ...timing, snapshotAt: 21000 }, 21200))
      .toContain("ACK 1100 мс · снимок +19800 мс · кадр +200 мс · всего 21100 мс");
  });
});
