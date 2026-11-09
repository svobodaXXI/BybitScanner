import { describe, expect, it } from "vitest";
import { manualMainReadProjection } from "./manualMainReadProjection";

const main = (account_id = "bybit-a") => ({
  account_id, environment: "MAINNET", status: "READY",
  refresh_generation: 2, wallet_balance_usdt: "100",
  total_equity_usdt: "105", available_balance_usdt: "91",
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
