import { fireEvent, render, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

describe("ModePanel account placement", () => {
  it("places the canonical account switch beside BUY and SELL LIMITS", () => {
    const onAccountToggle = vi.fn();
    const { container } = render(
      <ModePanel
        mode="TERMINAL"
        onModeChange={vi.fn()}
        symbol="BTCUSDT"
        paperState={null}
        activeLimitOrders={[]}
        refreshPaperState={vi.fn()}
        sizingReferencePrice="64000"
        authoritativeTickSize="0.5"
        limitDraftState={EMPTY_LIMIT_DRAFT_STATE}
        dispatchLimitDraft={vi.fn()}
        onLimitDraftConfirm={vi.fn()}
        onPositionSideChange={vi.fn()}
        accountOpen={false}
        onAccountToggle={onAccountToggle}
      />,
    );
    const limits = container.querySelector<HTMLElement>(".paper-limits-shell")!;
    expect(within(limits).getByText(/BUY LIMITS/)).toBeInTheDocument();
    expect(within(limits).getByText(/SELL LIMITS/)).toBeInTheDocument();
    expect(
      within(limits).getByRole("button", {
        name: "Cancel all Buy Limit orders for BTCUSDT",
      }),
    ).toHaveClass("paper-limits-cancel-all", "buy");
    expect(
      within(limits).getByRole("button", {
        name: "Cancel all Sell Limit orders for BTCUSDT",
      }),
    ).toHaveClass("paper-limits-cancel-all", "sell");
    fireEvent.click(within(limits).getByRole("button", { name: "Open account selection" }));
    expect(onAccountToggle).toHaveBeenCalledOnce();
  });
});
