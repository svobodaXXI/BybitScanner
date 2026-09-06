import { describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { executePaperMarketCommand } from "./paperMarketCommand";

const paperState: PaperState = {
  ok: true,
  state_revision: 2,
  account_id: "paper-old",
  symbol: "BTCUSDT",
  initial_deposit_usdt: "5000",
  equity_usdt: "5000",
  one_wv_usdt: "250",
  position_side: "Long",
  position_quantity: "1",
  average_entry: "100",
  engaged_notional_usdt: "100",
  engaged_wv: "0.4",
  active_limit_orders: [],
  protection: {
    status: "no_protection_configured",
    take_profit: null,
    stop_loss: null,
    trailing_stop: null,
    pending_command_id: null,
    warning: null,
    effective_quantity: null,
  },
};

describe("executePaperMarketCommand authority fencing", () => {
  it("fails closed when the authoritative PAPER state is rejected by the current session", async () => {
    const fetcher = vi.fn().mockResolvedValue({
      json: async () => ({
        status: "completed",
        reason_code: "OK",
        paper_state: paperState,
      }),
    });
    const applyPaperState = vi.fn(() => false);

    await expect(executePaperMarketCommand(
      {
        client_action_id: "market-stale-session",
        symbol: "BTCUSDT",
        side: "Buy",
        volume: { unit: "usdt", amount: "100" },
        sizing_reference_price: "100",
        slippage_type: "Percent",
        slippage_value: "0.5",
      },
      {
        fetcher: fetcher as unknown as typeof fetch,
        applyPaperState,
      },
    )).rejects.toThrow("paper_market_authoritative_state_rejected");

    expect(applyPaperState).toHaveBeenCalledOnce();
    expect(applyPaperState).toHaveBeenCalledWith(paperState);
  });
});
