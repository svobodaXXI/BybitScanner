import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

describe("ModePanel account placement", () => {
  it.each([true, false])(
    "isolates the lower account column from upper controls (mutationsAllowed=%s)",
    (mutationsAllowed) => {
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
        mutationsAllowed={mutationsAllowed}
      />,
    );
    const upper = screen.getByRole("group", { name: "Manual trading controls" });
    const lower = container.querySelector<HTMLElement>(".paper-lower-actions-row")!;
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
    const accountSwitch = screen.getByRole("button", { name: "Open account selection" });
    expect(accountSwitch.querySelector(".account-switch-label")).not.toBeNull();
    expect(accountSwitch.closest(".paper-market-actions-shell")).not.toBeNull();
    expect(upper.contains(lower)).toBe(false);
    expect(upper.contains(accountSwitch)).toBe(false);
    expect(lower.contains(limits)).toBe(true);
    expect(lower.contains(accountSwitch)).toBe(true);
    expect(lower.lastElementChild).toBe(accountSwitch.closest(".mode-panel-account-control"));
    expect(accountSwitch.closest("fieldset")).toBeNull();
    expect(accountSwitch.closest(".paper-limits-shell")).toBeNull();
    expect(limits.compareDocumentPosition(accountSwitch) & Node.DOCUMENT_POSITION_FOLLOWING)
      .toBeTruthy();
    expect(container.querySelectorAll(".account-switch-key")).toHaveLength(1);
    fireEvent.click(accountSwitch);
    expect(onAccountToggle).toHaveBeenCalledOnce();
    },
  );
});
