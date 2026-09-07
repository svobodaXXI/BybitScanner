import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

const state = {
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
  active_limit_orders: [
    {
      order_id: "paper-limit-1",
      order_link_id: "link-1",
      symbol: "BTCUSDT",
      side: "Buy",
      price: "64000",
      quantity: "0.005",
      time_in_force: "GTC",
    },
  ],
} as PaperState;

const renderPanel = (onLimitCancel = vi.fn()) => render(
  <ModePanel
    mode="TERMINAL"
    onModeChange={vi.fn()}
    symbol="BTCUSDT"
    paperState={state}
    activeLimitOrders={state.active_limit_orders}
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

const openBuyInventory = () => {
  vi.useFakeTimers();
  const button = screen.getByRole("button", { name: "BUY LIMITS 1" });
  Object.assign(button, {
    setPointerCapture: vi.fn(),
    hasPointerCapture: vi.fn(() => true),
    releasePointerCapture: vi.fn(),
  });
  fireEvent.pointerDown(button, {
    pointerId: 1,
    pointerType: "touch",
    button: 0,
  });
  vi.advanceTimersByTime(500);
  fireEvent.pointerUp(button, {
    pointerId: 1,
    pointerType: "touch",
    button: 0,
  });
  return screen.getByLabelText("Active Buy Limit orders for BTCUSDT");
};

describe("ModePanel LIMITS inventory dismissal", () => {
  it("closes on outside pointerdown without cancelling an order", () => {
    const onLimitCancel = vi.fn();
    renderPanel(onLimitCancel);
    openBuyInventory();

    fireEvent.pointerDown(document.body);

    expect(screen.queryByLabelText("Active Buy Limit orders for BTCUSDT")).not.toBeInTheDocument();
    expect(onLimitCancel).not.toHaveBeenCalled();
  });

  it("uses the inventory header cross only to close the inventory", () => {
    const onLimitCancel = vi.fn();
    renderPanel(onLimitCancel);
    const inventory = openBuyInventory();

    fireEvent.click(within(inventory).getByRole("button", {
      name: "Close Buy Limit orders for BTCUSDT",
    }));

    expect(screen.queryByLabelText("Active Buy Limit orders for BTCUSDT")).not.toBeInTheDocument();
    expect(onLimitCancel).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", {
      name: "Cancel all LONG Limit orders for BTCUSDT?",
    })).not.toBeInTheDocument();
  });
});
