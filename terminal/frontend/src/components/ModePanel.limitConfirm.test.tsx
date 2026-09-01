import { fireEvent, render, screen, within } from "@testing-library/react";
import { useReducer, useState } from "react";
import { expect, it, vi } from "vitest";
import { PendingLimitLine } from "../chart/PendingLimitLine";
import type { PaperState } from "../contracts/trading";
import type { AccountWorkspaceProjection } from "../accountWorkspace/accountWorkspaceStore";
import {
  EMPTY_LIMIT_DRAFT_STATE,
  limitDraftReducer,
} from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

const paperState: PaperState = {
  ok: true,
  state_revision: 1,
  account_id: "paper",
  symbol: "ONGUSDT",
  initial_deposit_usdt: "5000",
  equity_usdt: "5000",
  one_wv_usdt: "250",
  position_side: "Flat",
  position_quantity: "0",
  average_entry: null,
  engaged_notional_usdt: "0",
  engaged_wv: "0.0",
  active_limit_orders: [],
};

it("exposes the pending BUY Limit checkmark and submits exactly once", () => {
  const submit = vi.fn();

  function Harness() {
    const [limitDraftState, dispatchLimitDraft] = useReducer(
      limitDraftReducer,
      EMPTY_LIMIT_DRAFT_STATE,
    );

    return (
      <>
        <ModePanel
          mode="TERMINAL"
          onModeChange={vi.fn()}
          symbol="ONGUSDT"
          paperState={paperState}
          activeLimitOrders={[]}
          refreshPaperState={vi.fn()}
          sizingReferencePrice="0.1"
          authoritativeTickSize="0.00001"
          limitDraftState={limitDraftState}
          dispatchLimitDraft={dispatchLimitDraft}
          onLimitDraftConfirm={submit}
          onPositionSideChange={vi.fn()}
        />
        {limitDraftState.draft ? (
          <PendingLimitLine
            side={limitDraftState.draft.side}
            price={limitDraftState.draft.price}
            top={120}
            onDragClientY={vi.fn()}
            onConfirm={submit}
          />
        ) : null}
      </>
    );
  }

  render(<Harness />);
  const buyLimits = screen.getByRole("button", { name: "BUY LIMITS 0" });
  expect(screen.getByRole("button", { name: "BUY" })).toBeEnabled();
  expect(buyLimits).toBeEnabled();
  fireEvent.pointerDown(buyLimits);
  fireEvent.pointerUp(buyLimits);
  fireEvent.click(buyLimits);

  const popup = screen.getByRole("dialog", { name: "New Buy Limit" });
  expect(within(popup).getByText("LONG")).toBeInTheDocument();
  const confirm = screen.getByRole("button", {
    name: "Confirm pending Buy Limit",
  });
  fireEvent.click(confirm);

  expect(submit).toHaveBeenCalledTimes(1);
});

it.each(["READY", "READ_ONLY"] as const)(
  "renders disabled LIVE %s controls without account inventory cards",
  async (status) => {
  const liveProjection: AccountWorkspaceProjection = {
    ok: true,
    account_id: "bybit-main",
    provider: "BYBIT",
    environment: "MAINNET",
    status,
    session_generation: 8,
    projection_generation: 3,
    read_only: true,
    wallet_balance_usdt: "90",
    total_equity_usdt: "100",
    available_balance_usdt: "70",
    positions: [{ symbol: "BTCUSDT", side: "Long", size: "1" }],
    orders: [{ order_id: "o1", symbol: "ETHUSDT", side: "Buy", quantity: "2", price: "2000" }],
    paper_state: null,
  };
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      ok: true,
      active_account_id: "bybit-main",
      session_generation: 8,
      accounts: [{
        id: "bybit-main", display_name: "Main Bybit", provider: "BYBIT",
        environment: "MAINNET", status,
      }],
    }),
  });
  vi.stubGlobal("fetch", fetchMock);

  function Harness() {
    const [accountOpen, setAccountOpen] = useState(false);
    const [canMutate, setCanMutate] = useState(false);
    return <>
      <button onClick={() => setCanMutate(true)} type="button">Restore PAPER</button>
      <ModePanel
      mode="TERMINAL"
      onModeChange={vi.fn()}
      symbol="BTCUSDT"
      paperState={canMutate ? paperState : null}
      activeLimitOrders={[]}
      refreshPaperState={vi.fn()}
      sizingReferencePrice="100"
      authoritativeTickSize="0.5"
      limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
      dispatchLimitDraft={vi.fn()}
      onLimitDraftConfirm={vi.fn()}
      onPositionSideChange={vi.fn()}
      accountOpen={accountOpen}
      onAccountToggle={() => setAccountOpen((current) => !current)}
      accountWorkspaceProjection={canMutate ? null : liveProjection}
      mutationsAllowed={canMutate}
    />
    </>;
  }

  render(<Harness />);
  expect(screen.queryByText("LIVE READ-ONLY")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("LIVE account positions and orders")).not.toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Manual trading controls" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "BUY" })).toBeVisible();
  expect(screen.getByRole("button", { name: "BUY" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "SELL" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "BUY LIMITS 0" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "SELL LIMITS 0" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "STOP" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "TAKE" })).toBeDisabled();
  const accountKey = screen.getByRole("button", { name: "Open account selection" });
  expect(accountKey.closest(".paper-market-actions-shell")).not.toBeNull();
  expect(accountKey.closest("fieldset")).toBeNull();
  expect(document.querySelectorAll(".account-switch-key")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "BUY" }));
  fireEvent.click(screen.getByRole("button", { name: "STOP" }));
  expect(fetchMock.mock.calls.every(([, options]) => options?.method === undefined)).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Open account selection" }));
  expect(await screen.findByRole("dialog", { name: "Accounts" })).toBeInTheDocument();
  expect(screen.queryByLabelText("LIVE account positions and orders")).not.toBeInTheDocument();
  expect(screen.queryByText(/Equity 100|Wallet 90|BTCUSDT|ETHUSDT/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Close Accounts" }));
  fireEvent.click(screen.getByRole("button", { name: "Restore PAPER" }));
  expect(screen.getByRole("group", { name: "Manual trading controls" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "BUY" })).toBeEnabled();
  },
);
