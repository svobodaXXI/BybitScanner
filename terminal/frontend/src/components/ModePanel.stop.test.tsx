import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { PaperState } from "../contracts/trading";
import { EMPTY_LIMIT_DRAFT_STATE } from "../orders/limitDraft";
import { ModePanel } from "./ModePanel";

const state: PaperState = {
  ok: true, state_revision: 1, account_id: "paper", symbol: "BTCUSDT",
  initial_deposit_usdt: "5000", equity_usdt: "5000", one_wv_usdt: "250",
  position_side: "Long", position_quantity: "2", average_entry: "100",
  engaged_notional_usdt: "200", engaged_wv: "1", active_limit_orders: [],
};

const renderPanel = (stopActive: boolean, onStopTap = vi.fn(), onStopHold = vi.fn()) => render(
  <ModePanel
    mode="TERMINAL" onModeChange={vi.fn()} symbol="BTCUSDT" paperState={state}
    activeLimitOrders={[]} refreshPaperState={async () => {}}
    sizingReferencePrice="100" authoritativeTickSize="0.5"
    limitDraftState={EMPTY_LIMIT_DRAFT_STATE} dispatchLimitDraft={vi.fn()}
    onLimitDraftConfirm={vi.fn()} onPositionSideChange={vi.fn()}
    stopActive={stopActive} onStopTap={onStopTap} onStopHold={onStopHold}
  />,
);

it("uses short-tap STOP activation and derives red dot only from authoritative active prop", () => {
  const onStopTap = vi.fn();
  const view = renderPanel(false, onStopTap);
  fireEvent.click(screen.getByRole("button", { name: "STOP" }));
  expect(onStopTap).toHaveBeenCalledOnce();
  expect(document.querySelector(".paper-stop-active-dot")).toBeNull();

  view.rerender(
    <ModePanel
      mode="TERMINAL" onModeChange={vi.fn()} symbol="BTCUSDT" paperState={state}
      activeLimitOrders={[]} refreshPaperState={async () => {}}
      sizingReferencePrice="100" authoritativeTickSize="0.5"
      limitDraftState={EMPTY_LIMIT_DRAFT_STATE} dispatchLimitDraft={vi.fn()}
      onLimitDraftConfirm={vi.fn()} onPositionSideChange={vi.fn()}
      stopActive onStopTap={onStopTap}
    />,
  );
  expect(document.querySelector(".paper-stop-active-dot")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "STOP" })).toHaveAttribute("aria-pressed", "true");
});

it("opens STOP settings only after the 500ms hold and hides them on confirmed FLAT", () => {
  vi.useFakeTimers();
  const onStopTap = vi.fn();
  const onStopHold = vi.fn();
  const view = renderPanel(false, onStopTap, onStopHold);
  const button = screen.getByRole("button", { name: "STOP" });
  fireEvent.pointerDown(button, { pointerId: 1, pointerType: "mouse", button: 0 });
  vi.advanceTimersByTime(499);
  expect(onStopHold).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);
  expect(onStopHold).toHaveBeenCalledOnce();
  expect(onStopTap).not.toHaveBeenCalled();
  fireEvent.pointerUp(button, { pointerId: 1, pointerType: "mouse", button: 0 });

  view.rerender(
    <ModePanel
      mode="TERMINAL" onModeChange={vi.fn()} symbol="BTCUSDT"
      paperState={{ ...state, position_side: "Flat", position_quantity: "0", average_entry: null }}
      activeLimitOrders={[]} refreshPaperState={async () => {}}
      sizingReferencePrice="100" authoritativeTickSize="0.5"
      limitDraftState={EMPTY_LIMIT_DRAFT_STATE} dispatchLimitDraft={vi.fn()}
      onLimitDraftConfirm={vi.fn()} onPositionSideChange={vi.fn()}
      stopSettingsOpen onStopTap={onStopTap} onStopHold={onStopHold}
    />,
  );
  expect(screen.queryByRole("dialog", { name: "STOP settings" })).toBeNull();
  vi.useRealTimers();
});

it("shows the explicit current-market reference when active STOP settings are open", () => {
  render(
    <ModePanel
      mode="TERMINAL" onModeChange={vi.fn()} symbol="BTCUSDT" paperState={state}
      activeLimitOrders={[]} refreshPaperState={async () => {}}
      sizingReferencePrice="101" authoritativeTickSize="0.5"
      limitDraftState={EMPTY_LIMIT_DRAFT_STATE} dispatchLimitDraft={vi.fn()}
      onLimitDraftConfirm={vi.fn()} onPositionSideChange={vi.fn()}
      stopActive stopSettingsOpen stopReferencePrice="101"
    />,
  );
  expect(screen.getByRole("dialog", { name: "STOP settings" })).toHaveTextContent("Reference 101");
});

it("derives TAKE green dot from authority and reuses hold settings with current reference", () => {
  const onTakeTap = vi.fn();
  render(
    <ModePanel
      mode="TERMINAL" onModeChange={vi.fn()} symbol="BTCUSDT" paperState={state}
      activeLimitOrders={[]} refreshPaperState={async () => {}}
      sizingReferencePrice="101" authoritativeTickSize="0.5"
      limitDraftState={EMPTY_LIMIT_DRAFT_STATE} dispatchLimitDraft={vi.fn()}
      onLimitDraftConfirm={vi.fn()} onPositionSideChange={vi.fn()}
      takeActive takeSettingsOpen takeReferencePrice="101" onTakeTap={onTakeTap}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "TAKE" }));
  expect(onTakeTap).toHaveBeenCalledOnce();
  expect(document.querySelector(".paper-take-active-dot")).toBeInTheDocument();
  expect(screen.getByRole("dialog", { name: "TAKE settings" })).toHaveTextContent("Reference 101");
});

it("opens TAKE settings through the shared 500ms hold activation", () => {
  vi.useFakeTimers();
  const onTakeTap = vi.fn();
  const onTakeHold = vi.fn();
  render(
    <ModePanel
      mode="TERMINAL" onModeChange={vi.fn()} symbol="BTCUSDT" paperState={state}
      activeLimitOrders={[]} refreshPaperState={async () => {}}
      sizingReferencePrice="100" authoritativeTickSize="0.5"
      limitDraftState={EMPTY_LIMIT_DRAFT_STATE} dispatchLimitDraft={vi.fn()}
      onLimitDraftConfirm={vi.fn()} onPositionSideChange={vi.fn()}
      onTakeTap={onTakeTap} onTakeHold={onTakeHold}
    />,
  );
  const button = screen.getByRole("button", { name: "TAKE" });
  fireEvent.pointerDown(button, { pointerId: 7, pointerType: "mouse", button: 0 });
  vi.advanceTimersByTime(500);
  expect(onTakeHold).toHaveBeenCalledOnce();
  expect(onTakeTap).not.toHaveBeenCalled();
  fireEvent.pointerUp(button, { pointerId: 7, pointerType: "mouse", button: 0 });
  vi.useRealTimers();
});
