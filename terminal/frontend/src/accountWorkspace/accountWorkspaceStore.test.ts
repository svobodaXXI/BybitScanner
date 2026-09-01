import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountWorkspaceStore } from "./accountWorkspaceStore";

const projection = (accountId: string, generation: number) => ({
  ok: true as const, account_id: accountId, provider: accountId === "paper" ? "PAPER" as const : "BYBIT" as const,
  environment: accountId === "paper" ? "PAPER" : "MAINNET", status: "READY",
  session_generation: generation, projection_generation: 1,
  read_only: accountId !== "paper", wallet_balance_usdt: "100",
  total_equity_usdt: "100", available_balance_usdt: "90",
  positions: [], orders: [], paper_state: null,
});

afterEach(() => vi.restoreAllMocks());

describe("AccountWorkspaceStore", () => {
  it("refreshes an active LIVE snapshot and publishes the newer equity generation", async () => {
    const initial = projection("bybit-1", 2);
    const updated = { ...initial, projection_generation: 2, total_equity_usdt: "80",
      available_balance_usdt: "80" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => initial })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => updated });
    vi.stubGlobal("fetch", fetchMock);
    const store = new AccountWorkspaceStore();
    store.setSymbol("BTCUSDT");
    await vi.waitFor(() => expect(store.getSnapshot().projection).toEqual(initial));

    await store.refreshActiveLive();

    expect(store.getSnapshot().projection).toEqual(updated);
    expect(fetchMock.mock.calls.slice(1)).toEqual([
      ["/api/accounts/bybit-1/refresh", { method: "POST" }],
      ["/api/workspace/account?symbol=BTCUSDT"],
    ]);
  });

  it("rejects an older projection generation and preserves the latest LIVE snapshot", async () => {
    const latest = { ...projection("bybit-1", 2), projection_generation: 8 };
    const stale = { ...latest, projection_generation: 7, total_equity_usdt: "stale" };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => latest })
      .mockResolvedValueOnce({ ok: true, json: async () => stale }));
    const store = new AccountWorkspaceStore();
    store.setSymbol("BTCUSDT");
    await vi.waitFor(() => expect(store.getSnapshot().projection).toEqual(latest));

    await store.refresh();

    expect(store.getSnapshot().projection).toEqual(latest);
  });

  it("does not apply a LIVE refresh after an account switch starts", async () => {
    let resolveRefresh!: (value: unknown) => void;
    const initial = projection("bybit-1", 2);
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => initial })
      .mockReturnValueOnce(new Promise((resolve) => { resolveRefresh = resolve; }))
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        ok: true, active_account_id: "paper", session_generation: 3, status: "READY",
      }) })
      .mockResolvedValueOnce({ ok: true, json: async () => projection("paper", 3) }));
    const store = new AccountWorkspaceStore();
    store.setSymbol("BTCUSDT");
    await vi.waitFor(() => expect(store.getSnapshot().projection).toEqual(initial));
    const liveRefresh = store.refreshActiveLive();
    const switching = store.activate("paper");
    resolveRefresh({ ok: true, json: async () => ({ ok: true }) });
    await liveRefresh;
    await switching;

    expect(store.getSnapshot().projection?.account_id).toBe("paper");
    expect(store.getSnapshot().projection?.session_generation).toBe(3);
  });

  it("preserves the last valid LIVE projection when periodic reconciliation fails", async () => {
    const initial = projection("bybit-1", 2);
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => initial })
      .mockRejectedValueOnce(new Error("network")));
    const store = new AccountWorkspaceStore();
    store.setSymbol("BTCUSDT");
    await vi.waitFor(() => expect(store.getSnapshot().projection).toEqual(initial));

    await store.refreshActiveLive();

    expect(store.getSnapshot().projection).toEqual(initial);
  });

  it("coalesces overlapping cadence ticks into one LIVE REST refresh", async () => {
    let resolveRefresh!: (value: unknown) => void;
    const initial = projection("bybit-1", 2);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => initial })
      .mockReturnValueOnce(new Promise((resolve) => { resolveRefresh = resolve; }))
      .mockResolvedValueOnce({ ok: true, json: async () => initial });
    vi.stubGlobal("fetch", fetchMock);
    const store = new AccountWorkspaceStore();
    store.setSymbol("BTCUSDT");
    await vi.waitFor(() => expect(store.getSnapshot().projection).toEqual(initial));

    const first = store.refreshActiveLive();
    await store.refreshActiveLive();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    resolveRefresh({ ok: true, json: async () => ({ ok: true }) });
    await first;
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("clears the old projection and rejects a late response from the previous session", async () => {
    let resolveOld!: (value: unknown) => void;
    const oldResponse = new Promise((resolve) => { resolveOld = resolve; });
    const fetchMock = vi.fn()
      .mockReturnValueOnce(oldResponse)
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        ok: true, active_account_id: "bybit-1", session_generation: 2, status: "READY",
      }) })
      .mockResolvedValueOnce({ ok: true, json: async () => projection("bybit-1", 2) });
    vi.stubGlobal("fetch", fetchMock);
    const store = new AccountWorkspaceStore();
    store.setSymbol("BTCUSDT");
    const activation = store.activate("bybit-1");
    await activation;
    expect(store.getSnapshot().projection?.account_id).toBe("bybit-1");
    resolveOld({ ok: true, json: async () => projection("paper", 1) });
    await Promise.resolve();
    await Promise.resolve();
    expect(store.getSnapshot().projection?.account_id).toBe("bybit-1");
  });

  it("blocks duplicate activation while switching", async () => {
    let resolveSwitch!: (value: unknown) => void;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise((resolve) => { resolveSwitch = resolve; })));
    const store = new AccountWorkspaceStore();
    const first = store.activate("bybit-1");
    await expect(store.activate("paper")).rejects.toThrow("account_switch_in_progress");
    resolveSwitch({ ok: false, json: async () => ({ ok: false }) });
    await expect(first).rejects.toThrow();
  });

  it("rejects a stale switch result and preserves the prior projection", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => projection("paper", 2) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        ok: true, active_account_id: "bybit-1", session_generation: 2, status: "READY",
      }) });
    vi.stubGlobal("fetch", fetchMock);
    const store = new AccountWorkspaceStore();
    store.setSymbol("BTCUSDT");
    await vi.waitFor(() => expect(store.getSnapshot().projection?.account_id).toBe("paper"));

    await expect(store.activate("bybit-1")).rejects.toThrow("stale_account_switch");
    expect(store.getSnapshot().projection?.account_id).toBe("paper");
    expect(store.getSnapshot().switching).toBe(false);
  });

  it("keeps a successful switch authoritative when the new projection is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        ok: true, active_account_id: "bybit-1", session_generation: 2, status: "READY",
      }) })
      .mockRejectedValueOnce(new Error("network")));
    const store = new AccountWorkspaceStore();

    await expect(store.activate("bybit-1")).resolves.toMatchObject({
      active_account_id: "bybit-1", session_generation: 2,
    });
    expect(store.getSnapshot()).toEqual({ projection: null, switching: false });
  });

  it("preserves frontend ownership when activation is not found", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => projection("paper", 5) })
      .mockResolvedValueOnce({ ok: false, json: async () => ({
        ok: false, error: "account_not_found",
      }) }));
    const store = new AccountWorkspaceStore();
    store.setSymbol("BTCUSDT");
    await vi.waitFor(() => expect(store.getSnapshot().projection?.account_id).toBe("paper"));

    await expect(store.activate("Main Bybit")).rejects.toThrow("account_not_found");
    expect(store.getSnapshot().projection?.account_id).toBe("paper");
    expect(store.getSnapshot().projection?.session_generation).toBe(5);
  });
});
