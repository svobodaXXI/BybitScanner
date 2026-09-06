import { describe, expect, it } from "vitest";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import { projectLiveProtectionPosition } from "./liveProtectionProjection";

const liveProjection = (positions: Array<Record<string, unknown>>): AccountWorkspaceProjection => ({
  ok: true,
  account_id: "bybit-main",
  provider: "BYBIT",
  environment: "MAINNET",
  status: "READY",
  session_generation: 7,
  projection_generation: 11,
  read_only: false,
  capabilities: { market: true, limit: true, stop: true, take: true, full_close: true },
  wallet_balance_usdt: "1000",
  total_equity_usdt: "1000",
  available_balance_usdt: "900",
  positions,
  orders: [],
  paper_state: null,
});

describe("projectLiveProtectionPosition", () => {
  it("projects authoritative STOP/TAKE for the requested open LIVE position", () => {
    expect(projectLiveProtectionPosition(liveProjection([{
      symbol: "BTCUSDT",
      side: "Long",
      size: "0.01",
      average_entry: "64000",
      stop_loss: "62000",
      take_profit: "68000",
    }]), "BTCUSDT")).toEqual({
      side: "Long",
      averageEntry: "64000",
      stopLoss: "62000",
      takeProfit: "68000",
    });
  });

  it("fails closed for missing, flat, or non-BYBIT evidence", () => {
    expect(projectLiveProtectionPosition(liveProjection([]), "BTCUSDT")).toBeNull();
    expect(projectLiveProtectionPosition(liveProjection([{
      symbol: "BTCUSDT", side: "Long", size: "0", average_entry: "64000",
    }]), "BTCUSDT")).toBeNull();
    expect(projectLiveProtectionPosition({ ...liveProjection([]), provider: "PAPER", environment: "PAPER" }, "BTCUSDT")).toBeNull();
  });
});
