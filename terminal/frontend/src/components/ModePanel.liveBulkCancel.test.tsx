import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import type { PaperLimitOrder } from "../contracts/trading";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

const projection = (sessionGeneration: number): AccountWorkspaceProjection => ({
  ok: true,
  account_id: "bybit-main",
  provider: "BYBIT",
  environment: "MAINNET",
  status: "READY",
  session_generation: sessionGeneration,
  projection_generation: sessionGeneration,
  read_only: false,
  capabilities: {
    market: false,
    limit: true,
    stop: false,
    take: false,
    full_close: false,
  },
  wallet_balance_usdt: "1000",
  total_equity_usdt: "1000",
  available_balance_usdt: "1000",
  one_wv_usdt: "50",
  positions: [],
  orders: [],
  paper_state: null,
});

const order = (orderId: string): PaperLimitOrder => ({
  order_id: orderId,
  order_link_id: `link-${orderId}`,
  symbol: "BTCUSDT",
  side: "Buy",
  price: "64000",
  quantity: "0.001",
  time_in_force: "GTC",
});

const panel = (
  sessionGeneration: number,
  activeLimitOrders: PaperLimitOrder[],
  onLimitCancel: (orderId: string) => Promise<{ status: string } | null>,
) => (
  <ModePanel
    mode="TERMINAL"
    onModeChange={vi.fn()}
    symbol="BTCUSDT"
    paperState={null}
    activeLimitOrders={activeLimitOrders}
    refreshPaperState={vi.fn()}
    sizingReferencePrice="64500"
    authoritativeTickSize="0.5"
    limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
    dispatchLimitDraft={vi.fn()}
    onLimitDraftConfirm={vi.fn()}
    onLimitCancel={onLimitCancel}
    onPositionSideChange={vi.fn()}
    accountWorkspaceProjection={projection(sessionGeneration)}
    mutationsAllowed={false}
    liveLimitAllowed
  />
);

const confirmCancelAll = () => {
  fireEvent.click(screen.getByRole("button", {
    name: "Cancel all Buy Limit orders for BTCUSDT",
  }));
  const dialog = screen.getByRole("dialog", {
    name: "Cancel all LONG Limit orders for BTCUSDT?",
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "CANCEL" }));
};

it("lets a new LIVE authority start bulk cancel while the previous authority is still unresolved", async () => {
  let resolveOld!: (value: { status: string }) => void;
  let resolveNew!: (value: { status: string }) => void;
  const onLimitCancel = vi.fn((orderId: string) => new Promise<{ status: string }>((resolve) => {
    if (orderId === "old-order") resolveOld = resolve;
    if (orderId === "new-order") resolveNew = resolve;
  }));

  const view = render(panel(7, [order("old-order")], onLimitCancel));
  confirmCancelAll();
  await waitFor(() => expect(onLimitCancel).toHaveBeenCalledTimes(1));

  view.rerender(panel(8, [order("new-order")], onLimitCancel));
  confirmCancelAll();

  await waitFor(() => expect(onLimitCancel).toHaveBeenCalledTimes(2));
  expect(onLimitCancel.mock.calls[1][0]).toBe("new-order");

  resolveOld({ status: "completed" });
  await Promise.resolve();

  confirmCancelAll();
  expect(onLimitCancel).toHaveBeenCalledTimes(2);

  resolveNew({ status: "completed" });
});
