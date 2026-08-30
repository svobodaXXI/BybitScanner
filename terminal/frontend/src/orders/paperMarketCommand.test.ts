import { describe, expect, it, vi } from "vitest";
import {
  domSelectionRequiresMarket,
  executePaperMarketCommand,
} from "./paperMarketCommand";

describe("domSelectionRequiresMarket", () => {
  it("routes BUY crossing Ask to Market and keeps resting BUY as Limit", () => {
    expect(domSelectionRequiresMarket("Buy", "99", 99, 100)).toBe(false);
    expect(domSelectionRequiresMarket("Buy", "100", 99, 100)).toBe(true);
    expect(domSelectionRequiresMarket("Buy", "101", 99, 100)).toBe(true);
  });

  it("routes SELL crossing Bid to Market and keeps resting SELL as Limit", () => {
    expect(domSelectionRequiresMarket("Sell", "101", 100, 101)).toBe(false);
    expect(domSelectionRequiresMarket("Sell", "100", 100, 101)).toBe(true);
    expect(domSelectionRequiresMarket("Sell", "99", 100, 101)).toBe(true);
  });

  it("does not infer Market when the required opposite quote is unavailable", () => {
    expect(domSelectionRequiresMarket("Buy", "100", 99, undefined)).toBe(false);
    expect(domSelectionRequiresMarket("Sell", "100", undefined, 101)).toBe(false);
  });
});

describe("executePaperMarketCommand", () => {
  it("uses the canonical /api/market endpoint and applies completed state", async () => {
    const paperState = {
      ok: true,
      state_revision: 2,
      account_id: "paper",
      symbol: "OGUSDT",
      initial_deposit_usdt: "5000",
      equity_usdt: "5000",
      one_wv_usdt: "250",
      position_side: "Long",
      position_quantity: "1",
      average_entry: "1",
      engaged_notional_usdt: "250",
      engaged_wv: "1.0",
      active_limit_orders: [],
    };

    const fetcher = vi.fn().mockResolvedValue({
      json: async () => ({
        status: "completed",
        reason_code: "OK",
        paper_state: paperState,
      }),
    });
    const applyPaperState = vi.fn();

    await executePaperMarketCommand(
      {
        client_action_id: "market-1",
        symbol: "OGUSDT",
        side: "Buy",
        volume: { unit: "usdt", amount: "250" },
        sizing_reference_price: "1",
        slippage_type: "Percent",
        slippage_value: "0.5",
      },
      {
        fetcher: fetcher as unknown as typeof fetch,
        applyPaperState,
      },
    );

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/market",
      expect.objectContaining({ method: "POST" }),
    );
    expect(applyPaperState).toHaveBeenCalledTimes(1);
    expect(applyPaperState).toHaveBeenCalledWith(paperState);
  });
});
