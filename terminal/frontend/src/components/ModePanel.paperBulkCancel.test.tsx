import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { PaperLimitOrder, PaperState } from "../contracts/trading";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

const limit = (index: number): PaperLimitOrder => ({
  order_id: `paper-limit-${index}`,
  order_link_id: `link-${index}`,
  symbol: "BTCUSDT",
  side: "Buy",
  price: String(64000 - index * 10),
  quantity: "0.005",
  time_in_force: "GTC",
});

it("cancels all five Buy PAPER limits after one side confirmation", async () => {
  const limits = Array.from({ length: 5 }, (_, index) => limit(index + 1));
  const state: PaperState = {
    state_revision: 1,
    ok: true,
    account_id: "paper",
    symbol: "BTCUSDT",
    initial_deposit_usdt: "5000",
    equity_usdt: "5000",
    engaged_wv: "0",
    engaged_notional_usdt: "0",
    one_wv_usdt: "250",
    position_side: "Flat",
    position_quantity: "0",
    average_entry: null,
    active_limit_orders: limits,
  };
  const onLimitCancel = vi.fn().mockResolvedValue({
    status: "completed",
    reason_code: "completed",
  });

  render(
    <ModePanel
      mode="TERMINAL"
      onModeChange={vi.fn()}
      symbol="BTCUSDT"
      paperState={state}
      activeLimitOrders={limits}
      refreshPaperState={vi.fn()}
      sizingReferencePrice="64250"
      authoritativeTickSize="0.5"
      limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
      dispatchLimitDraft={vi.fn()}
      onLimitDraftConfirm={vi.fn()}
      onLimitCancel={onLimitCancel}
      onPositionSideChange={vi.fn()}
    />,
  );

  fireEvent.click(screen.getByRole("button", {
    name: "Cancel all Buy Limit orders for BTCUSDT",
  }));
  const dialog = screen.getByRole("dialog", {
    name: "Cancel all LONG Limit orders for BTCUSDT?",
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "CANCEL" }));

  await waitFor(() => expect(onLimitCancel).toHaveBeenCalledTimes(5));
  expect(onLimitCancel.mock.calls.map(([orderId]) => orderId)).toEqual(
    limits.map((order) => order.order_id),
  );
});
