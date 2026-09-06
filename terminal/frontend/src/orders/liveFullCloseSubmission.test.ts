import { describe, expect, it, vi } from "vitest";
import { LiveFullCloseSubmissionController } from "./liveFullCloseSubmission";

const authority = () => ({ accountId: "bybit-main", sessionGeneration: 7 });

describe("LiveFullCloseSubmissionController", () => {
  it("deduplicates one semantic FULL_CLOSE attempt and reuses one client_action_id", async () => {
    let resolveResponse!: (response: Response) => void;
    const originalFetch = globalThis.fetch;
    const fetcher = vi.fn<typeof fetch>(() => new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    }));
    globalThis.fetch = fetcher;
    try {
      const controller = new LiveFullCloseSubmissionController();
      const createClientActionId = vi.fn(() => "live-close-1");
      const refreshActiveLive = vi.fn(async () => {});
      const first = controller.submit({ symbol: "BTCUSDT" }, {
        currentAuthority: authority, createClientActionId, refreshActiveLive,
      });
      const second = controller.submit({ symbol: "BTCUSDT" }, {
        currentAuthority: authority, createClientActionId, refreshActiveLive,
      });
      expect(first).toBe(second);
      expect(createClientActionId).toHaveBeenCalledOnce();
      expect(fetcher).toHaveBeenCalledOnce();
      resolveResponse(new Response(JSON.stringify({
        status: "accepted_pending", reason_code: "accepted_pending", command_id: "cmd-1",
        reconciliation_required: false,
      })));
      await first;
      expect(refreshActiveLive).toHaveBeenCalledOnce();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("retains ownership after UNKNOWN so a repeated gesture does not resend", async () => {
    const originalFetch = globalThis.fetch;
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({
      status: "unknown", reason_code: "mutation_unknown", command_id: "cmd-1",
      reconciliation_required: true,
    })));
    globalThis.fetch = fetcher;
    try {
      const controller = new LiveFullCloseSubmissionController();
      const deps = {
        currentAuthority: authority,
        createClientActionId: vi.fn(() => "live-close-1"),
        refreshActiveLive: vi.fn(async () => {}),
      };
      const first = controller.submit({ symbol: "BTCUSDT" }, deps);
      await first;
      const second = controller.submit({ symbol: "BTCUSDT" }, deps);
      expect(second).toBe(first);
      expect(fetcher).toHaveBeenCalledOnce();
      expect(deps.createClientActionId).toHaveBeenCalledOnce();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("retains ownership after a rejected transport promise", async () => {
    const originalFetch = globalThis.fetch;
    const fetcher = vi.fn<typeof fetch>(async () => { throw new Error("network"); });
    globalThis.fetch = fetcher;
    try {
      const controller = new LiveFullCloseSubmissionController();
      const deps = {
        currentAuthority: authority,
        createClientActionId: vi.fn(() => "live-close-1"),
        refreshActiveLive: vi.fn(async () => {}),
      };
      const first = controller.submit({ symbol: "BTCUSDT" }, deps);
      await expect(first).rejects.toThrow("network");
      const second = controller.submit({ symbol: "BTCUSDT" }, deps);
      expect(second).toBe(first);
      expect(fetcher).toHaveBeenCalledOnce();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
