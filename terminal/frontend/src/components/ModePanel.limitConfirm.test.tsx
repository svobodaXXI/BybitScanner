import { fireEvent, render, screen, within } from "@testing-library/react";
import { useReducer } from "react";
import { expect, it, vi } from "vitest";
import { PendingLimitLine } from "../chart/PendingLimitLine";
import type { PaperState } from "../contracts/trading";
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
  fireEvent.pointerDown(buyLimits);
  fireEvent.pointerUp(buyLimits);
  fireEvent.click(buyLimits);

  const popup = screen.getByRole("dialog", { name: "New Buy Limit" });
  fireEvent.click(within(popup).getByText("LONG / L"));

  expect(screen.queryByRole("dialog", { name: "New Buy Limit" })).not.toBeInTheDocument();
  const confirm = screen.getByRole("button", {
    name: "Confirm pending Buy Limit",
  });
  fireEvent.click(confirm);

  expect(submit).toHaveBeenCalledTimes(1);
});
