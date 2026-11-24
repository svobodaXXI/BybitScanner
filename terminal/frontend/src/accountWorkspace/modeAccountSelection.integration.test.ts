import "@testing-library/jest-dom/vitest";
import { renderHook, waitFor, act, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useModeAccountSelection } from "./modeAccountSelection";

const KEY = "bybitscanner.terminal.manualMainAccountId.v1";
const PREF = "/api/manual-main/terminal-preference";
const paper = { id: "paper", provider: "PAPER", display_name: "Paper", environment: "PAPER", status: "READY" };
const main = { id: "bybit-a", provider: "BYBIT", display_name: "Main", environment: "MAINNET", status: "DISCONNECTED" };
const snapshot = {
  account_id: "bybit-a", environment: "MAINNET", status: "READY",
  refresh_generation: 2, wallet_balance_usdt: "1",
  total_equity_usdt: "1", available_balance_usdt: "1",
  positions: [], orders: [],
};
function response(body: unknown, ok = true) {
  return { ok, json: async () => body };
}

function mockServer(initial: string | null) {
  const server = { selected: initial, connected: true, preferenceAvailable: true, writeAllowed: true, tradingEnabled: false };
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === PREF) {
      if (!server.preferenceAvailable) return response({ ok: false }, false);
      if (options?.method === "POST") {
        if (!server.writeAllowed) return response({ ok: false }, false);
        server.selected = JSON.parse(String(options.body)).account_id;
      }
      return response({ ok: true, account_id: server.selected });
    }
    if (url === "/api/accounts/mode-preferences")
      return response({ ok: true, preferences: { TERMINAL: "paper", AUTOPILOT: "paper" } });
    if (url === "/api/manual-main/accounts")
      return response({ ok: true, accounts: [main] });
    if (url === "/api/manual-main/accounts/bybit-a/refresh" && options?.method === "POST")
      return response({ ok: server.connected }, server.connected);
    if (url === "/api/manual-main/accounts/bybit-a/summary")
      return response({ ok: true, summary: { ...snapshot, trading_enabled: server.tradingEnabled } });
    throw new Error("unexpected API route " + url);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { server, fetchMock };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("restored per-mode account selection", () => {
  it("restores a server-bound MAIN without local storage, independently of Autopilot", async () => {
    const { fetchMock } = mockServer("bybit-a");
    const first = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(first.result.current.mainProjection?.account_id).toBe("bybit-a"));
    expect(first.result.current.preferences.AUTOPILOT).toBe("paper");
    expect(first.result.current.mainProjection?.read_only).toBe(true);
    first.unmount();
    window.localStorage.clear();
    const second = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(second.result.current.mainProjection?.account_id).toBe("bybit-a"));
    expect(second.result.current.preferences.TERMINAL).toBe("bybit-a");
    expect(fetchMock.mock.calls.some(([url, opts]) =>
      String(url).includes("/activate") || (url === PREF && opts?.method === "POST"))).toBe(false);
  });

  it("persists explicit MAIN and PAPER choices without changing Autopilot", async () => {
    const { server } = mockServer(null);
    const first = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(first.result.current.preferences.TERMINAL).toBe("paper"));
    await act(async () => { await first.result.current.selectAccount("TERMINAL", main); });
    expect(server.selected).toBe("bybit-a");
    first.unmount();
    window.localStorage.clear();
    const second = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(second.result.current.mainProjection?.account_id).toBe("bybit-a"));
    await act(async () => { await second.result.current.selectAccount("TERMINAL", paper); });
    expect(server.selected).toBe("paper");
    expect(second.result.current.preferences.AUTOPILOT).toBe("paper");
    second.unmount();
    window.localStorage.setItem(KEY, "bybit-a");
    const third = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(third.result.current.preferences.TERMINAL).toBe("paper"));
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it("migrates an existing local binding once when server has no binding", async () => {
    window.localStorage.setItem(KEY, "bybit-a");
    const { server } = mockServer(null);
    const { result } = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(result.current.mainProjection?.account_id).toBe("bybit-a"));
    expect(server.selected).toBe("bybit-a");
    expect(window.localStorage.getItem(KEY)).toBeNull();
  });

  it("keeps a disconnected MAIN selected and automatically retries", async () => {
    const { server } = mockServer("bybit-a");
    server.connected = false;
    const { result } = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(result.current.error).toContain("reconnecting"));
    expect(result.current.preferences.TERMINAL).toBe("bybit-a");
    expect(result.current.mainProjection).toBeNull();
    server.connected = true;
    await waitFor(() => expect(result.current.mainProjection?.account_id).toBe("bybit-a"), { timeout: 3000 });
    expect(result.current.error).toBeNull();
  });

  it("refreshes a connected read-only MAIN inventory, reconnects on failure and stops on PAPER", async () => {
    vi.useFakeTimers();
    const { server, fetchMock } = mockServer("bybit-a");
    const { result } = renderHook(() => useModeAccountSelection());
    const advance = async (ms: number) => {
      await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    };
    const reads = () => fetchMock.mock.calls.filter(([url, opts]) =>
      url === "/api/manual-main/accounts/bybit-a/refresh" && opts?.method === "POST").length;
    await advance(0);
    await advance(0);
    expect(result.current.mainProjection?.read_only).toBe(true);
    const initial = reads();
    await advance(15_000);
    expect(reads()).toBe(initial + 1);
    await advance(15_000);
    expect(reads()).toBe(initial + 2);
    server.connected = false;
    await advance(15_000);
    expect(result.current.mainProjection).toBeNull();
    expect(result.current.preferences.TERMINAL).toBe("bybit-a");
    server.connected = true;
    await advance(1000);
    expect(result.current.mainProjection?.read_only).toBe(true);
    await act(async () => { await result.current.selectAccount("TERMINAL", paper); });
    const before = reads();
    await advance(30_000);
    expect(reads()).toBe(before);
    expect(result.current.preferences.AUTOPILOT).toBe("paper");
  });

  it("does not rotate writable MAIN session generations in the inventory timer", async () => {
    vi.useFakeTimers();
    const { server, fetchMock } = mockServer("bybit-a");
    server.tradingEnabled = true;
    const { result } = renderHook(() => useModeAccountSelection());
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.mainProjection?.read_only).toBe(false);
    const reads = fetchMock.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(fetchMock.mock.calls).toHaveLength(reads);
  });

  it("never uses PAPER as fallback for an unavailable binding", async () => {
    const { server } = mockServer("bybit-a");
    server.preferenceAvailable = false;
    const { result } = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(result.current.preferences.AUTOPILOT).toBe("paper"));
    expect(result.current.preferences.TERMINAL).toBeNull();
    expect(result.current.mainProjection).toBeNull();
    server.preferenceAvailable = true;
    await waitFor(() => expect(result.current.mainProjection?.account_id).toBe("bybit-a"), { timeout: 3000 });
  });

  it("retains previous selection when a preference write is rejected", async () => {
    const { server } = mockServer("paper");
    const { result } = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(result.current.preferences.TERMINAL).toBe("paper"));
    server.writeAllowed = false;
    await act(async () => { await expect(result.current.selectAccount("TERMINAL", main)).rejects.toThrow(); });
    expect(result.current.preferences.TERMINAL).toBe("paper");
    expect(result.current.mainProjection).toBeNull();
    expect(server.selected).toBe("paper");
  });
});
