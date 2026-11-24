import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { manualMainReadProjection, parseMainExecutionHistory, useMainExecutionHistory } from "./manualMainReadProjection";
import { projectLiveProtectionPosition } from "../orders/liveProtectionProjection";

const main = (account_id = "bybit-a") => ({
  account_id, environment: "MAINNET", status: "READY",
  refresh_generation: 2, wallet_balance_usdt: "100",
  total_equity_usdt: "105", available_balance_usdt: "91", one_wv_usdt: "5",
  positions: [{ account_id, symbol: "BTCUSDT", side: "LONG", size: "1" }],
  orders: [{ account_id, symbol: "BTCUSDT" }],
});

describe("manual MAIN account inventory boundary", () => {
  it("keeps MAIN read-only until its independent gateway grants trading authority", () => {
    const result = manualMainReadProjection("bybit-a", main());
    expect(result?.positions).toHaveLength(1);
    expect(result?.account_id).toBe("bybit-a");
    expect(result?.read_only).toBe(true);
    expect(result?.capabilities).toEqual({
      market: false, limit: false, stop: false, take: false, full_close: false,
    });
    expect(result?.paper_state).toBeNull();
  });

  it("carries only authoritative MAIN sizing defaults, without deriving from equity or PAPER", () => {
    expect(manualMainReadProjection("bybit-a", main())?.one_wv_usdt).toBe("5");
    for (const value of [undefined, null, "0", "-1", "5.25", "NaN", 5]) {
      expect(manualMainReadProjection("bybit-a", { ...main(), one_wv_usdt: value })?.one_wv_usdt).toBeNull();
    }
  });

  it("enables MAIN manual controls only for a READY authenticated trading gateway snapshot", () => {
    const writable = manualMainReadProjection("bybit-a", { ...main(), trading_enabled: true });
    expect(writable?.read_only).toBe(false);
    expect(writable?.capabilities).toEqual({
      market: true, limit: true, stop: true, take: true, full_close: true,
    });
    const readOnly = manualMainReadProjection("bybit-a", {
      ...main(), status: "READ_ONLY", trading_enabled: true,
    });
    expect(readOnly?.read_only).toBe(true);
    expect(readOnly?.capabilities?.market).toBe(false);
    expect(manualMainReadProjection("bybit-a", {
      ...main(), trading_enabled: "true",
    })?.read_only).toBe(true);
  });

  it("never accepts stale, cross-account, PAPER or malformed evidence", () => {
    expect(manualMainReadProjection("bybit-b", main())).toBeNull();
    expect(manualMainReadProjection("bybit-a", { ...main(), environment: "PAPER" })).toBeNull();
    expect(manualMainReadProjection("bybit-a", { ...main(), status: "ERROR" })).toBeNull();
    expect(manualMainReadProjection("bybit-a", { ...main(), refresh_generation: 0 })).toBeNull();
    expect(manualMainReadProjection("bybit-a", {
      ...main(), positions: [{ account_id: "bybit-b", symbol: "ETHUSDT" }],
    })).toBeNull();
    expect(manualMainReadProjection("bybit-a", {
      ...main(), orders: [{ account_id: "paper", symbol: "ETHUSDT" }],
    })).toBeNull();
    expect(manualMainReadProjection("bybit-a", null)).toBeNull();
  });
});

describe("MAIN exact execution history", () => {
  const start = 1800000000000;
  const row = { exec_id: "fill-1", time_ms: start + 42, price: "65000.125", side: "Buy" };
  const payload = { ok: true, account_id: "bybit-a", symbol: "BTCUSDT", start_ms: start,
    end_ms: start + 604800000, executions: [row, row] };
  it("deduplicates actual fills, never invents markers or accepts wrong scope", () => {
    expect(parseMainExecutionHistory("bybit-a", "BTCUSDT", payload)?.markers)
      .toEqual([{ time_ms: row.time_ms, price: row.price, side: "Buy", filled: true }]);
    expect(parseMainExecutionHistory("bybit-b", "BTCUSDT", payload)).toBeNull();
    expect(parseMainExecutionHistory("bybit-a", "ETHUSDT", payload)).toBeNull();
    expect(parseMainExecutionHistory("bybit-a", "BTCUSDT", {
      ...payload, executions: [row, { ...row, price: "1" }],
    })).toBeNull();
    expect(parseMainExecutionHistory("bybit-a", "BTCUSDT", {
      ...payload, executions: [{ ...row, time_ms: start - 1 }],
    })).toBeNull();
    expect(parseMainExecutionHistory("bybit-a", "BTCUSDT", {
      ...payload, executions: [],
    })?.markers).toEqual([]);
  });
  it("reads the actual open position average without granting mutation permissions", () => {
    const projection = manualMainReadProjection("bybit-a", { ...main(), status: "READ_ONLY",
      positions: [{ account_id: "bybit-a", symbol: "BTCUSDT", side: "Long", size: "1", average_entry: "65000.125" }] });
    expect(projection?.capabilities?.stop).toBe(false);
    expect(projectLiveProtectionPosition(projection, "BTCUSDT")?.averageEntry).toBe("65000.125");
    expect(projectLiveProtectionPosition(projection, "ETHUSDT")).toBeNull();
  });
});

describe("MAIN history transient failures", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
  const setup = () => {
    vi.useFakeTimers();
    let status = 200;
    let badScope = false;
    const fetcher = vi.fn(async () => {
      const end = Date.now();
      return {
        ok: status === 200, status,
        json: async () => ({
          ok: true, account_id: badScope ? "bybit-b" : "bybit-a", symbol: "BTCUSDT",
          start_ms: end - 604800000, end_ms: end,
          executions: [{ exec_id: "fill-1", time_ms: end - 1000, price: "65000", side: "Buy" }],
        }),
      };
    });
    vi.stubGlobal("fetch", fetcher);
    const advance = async (ms: number) => {
      await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
    };
    return { advance, fail: (code: number) => { status = code; },
      rejectScope: () => { badScope = true; } };
  };
  it("retains verified fills with a stale status and expires them without a successful refresh", async () => {
    const { advance, fail } = setup();
    const { result } = renderHook(() => useMainExecutionHistory("bybit-a", "BTCUSDT"));
    await advance(0);
    expect(result.current.status).toBe("ready");
    expect(result.current.markers).toHaveLength(1);
    fail(503);
    await advance(30_000);
    expect(result.current.status).toBe("stale");
    expect(result.current.markers).toHaveLength(1);
    await advance(60_000);
    expect(result.current.status).toBe("unavailable");
    expect(result.current.markers).toHaveLength(0);
    fail(200);
    await advance(30_000);
    expect(result.current.status).toBe("ready");
    expect(result.current.markers).toHaveLength(1);
  });

  it("clears on authorization rejection, invalid identity, and account/symbol changes", async () => {
    const { advance, fail, rejectScope } = setup();
    const { result, rerender } = renderHook(
      ({ account, symbol }) => useMainExecutionHistory(account, symbol),
      { initialProps: { account: "bybit-a", symbol: "BTCUSDT" } },
    );
    await advance(0);
    expect(result.current.markers).toHaveLength(1);
    fail(403);
    await advance(30_000);
    expect(result.current.status).toBe("unavailable");
    expect(result.current.markers).toHaveLength(0);
    fail(200);
    await advance(30_000);
    expect(result.current.status).toBe("ready");
    rejectScope();
    await advance(30_000);
    expect(result.current.status).toBe("unavailable");
    expect(result.current.markers).toHaveLength(0);
    rerender({ account: "bybit-b", symbol: "ETHUSDT" });
    expect(result.current.markers).toHaveLength(0);
  });
});
