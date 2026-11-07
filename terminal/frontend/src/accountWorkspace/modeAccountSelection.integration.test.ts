import "@testing-library/jest-dom/vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useModeAccountSelection } from "./modeAccountSelection";

const KEY = "bybitscanner.terminal.manualMainAccountId.v1";
const paper = { id: "paper", provider: "PAPER", display_name: "Paper", environment: "PAPER", status: "READY" };
const main = { id: "bybit-a", provider: "BYBIT", display_name: "Main", environment: "MAINNET", status: "DISCONNECTED" };
const snapshot = {
  account_id: "bybit-a", environment: "MAINNET", status: "READY",
  refresh_generation: 2, wallet_balance_usdt: "1",
  total_equity_usdt: "1", available_balance_usdt: "1",
  positions: [], orders: [],
};
function response(body: unknown) {
  return { ok: true, json: async () => body };
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("restored per-mode account selection", () => {
  it("keeps Autopilot PAPER and restores MAIN from an independently refreshed read-only snapshot", async () => {
    window.localStorage.setItem(KEY, "bybit-a");
    const fetchMock = vi.fn(async (url: string, options?: { method?: string }) => {
      if (url === "/api/accounts/mode-preferences")
        return response({ ok: true, preferences: { TERMINAL: "paper", AUTOPILOT: "paper" } });
      if (url === "/api/manual-main/accounts")
        return response({ ok: true, accounts: [main] });
      if (url === "/api/manual-main/accounts/bybit-a/refresh" && options?.method === "POST")
        return response({ ok: true });
      if (url === "/api/manual-main/accounts/bybit-a/summary")
        return response({ ok: true, summary: snapshot });
      throw new Error("unexpected API route " + url);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(result.current.preferences.TERMINAL).toBe("bybit-a"));
    await waitFor(() => expect(result.current.mainProjection?.account_id).toBe("bybit-a"));
    expect(result.current.mainProjection?.read_only).toBe(true);
    expect(result.current.preferences.AUTOPILOT).toBe("paper");
    expect(fetchMock.mock.calls.some(([url, opts]) =>
      String(url).includes("/activate") || (String(url).includes("/refresh") && opts?.method !== "POST"))).toBe(false);
  });

  it("never substitutes PAPER when persisted MAIN cannot be verified", async () => {
    window.localStorage.setItem(KEY, "bybit-a");
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/accounts/mode-preferences")
        return response({ ok: true, preferences: { TERMINAL: "paper", AUTOPILOT: "paper" } });
      if (url === "/api/manual-main/accounts")
        return response({ ok: true, accounts: [] });
      throw new Error("unavailable");
    }));
    const { result } = renderHook(() => useModeAccountSelection());
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.preferences.TERMINAL).toBe("bybit-a");
    expect(result.current.mainProjection).toBeNull();
    expect(window.localStorage.getItem(KEY)).toBe("bybit-a");
  });
});
