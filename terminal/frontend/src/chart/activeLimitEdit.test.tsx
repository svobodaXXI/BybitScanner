import { fireEvent, render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ACTIVE_LIMIT_EDIT_HOLD_MS,
  cancelVisibleLimitCandidates,
  confirmVisibleLimitCandidates,
  useActiveLimitEdit,
} from "./activeLimitEdit";

function Harness({ amend = async () => {}, cancelOrder = async () => {}, onOtherActive = () => {}, onOtherPending = () => {} }: {
  amend?: (orderId: string, price: string) => Promise<void>;
  cancelOrder?: (orderId: string) => Promise<void>;
  onOtherActive?: () => void;
  onOtherPending?: () => void;
}) {
  const edit = useActiveLimitEdit({
    priceAtClientY: (clientY) => String(clientY),
    normalizePrice: (price) => price,
    amend,
    cancelOrder,
  });
  const activeCancelVisible = edit.state.mode === "ACTIVE_CANCEL" || (edit.state.mode === "CANCELLING" && edit.state.presentation === "ACTIVE");
  const editActionsVisible = edit.state.mode === "PENDING_CONFIRM" || edit.state.mode === "AMENDING" || (edit.state.mode === "CANCELLING" && edit.state.presentation === "EDIT");
  return <>
    <div
      data-active-limit-edit="order-1"
      data-testid="line"
      onPointerDown={(event) => edit.pointerDown(event, { order_id: "order-1", side: "Buy", price: "100" })}
      onPointerMove={edit.pointerMove}
      onPointerUp={edit.pointerUp}
      onPointerCancel={edit.pointerCancel}
    />
    <output>{edit.state.mode}:{edit.state.mode === "ACTIVE" ? "100" : edit.state.candidatePrice}</output>
    {activeCancelVisible ? <span>active-cancel-visible</span> : null}
    {editActionsVisible ? <button onClick={() => void edit.confirm()}>confirm</button> : null}
    {activeCancelVisible || editActionsVisible ? <button onClick={() => void edit.cancel()}>cancel</button> : null}
    <button data-active-limit-global-actions>global-candidate-control</button>
    <div data-active-limit-edit="order-2" data-testid="other-active" onPointerDown={onOtherActive} />
    <div data-pending-limit-line data-testid="other-pending" onPointerDown={onOtherPending} />
    <div data-testid="outside" />
  </>;
}

describe("active Limit edit controller", () => {
  afterEach(() => vi.useRealTimers());

  it("shows the solid ACTIVE cancel affordance after a short tap without entering edit", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 9, button: 0, clientX: 10, clientY: 10 });
    expect(screen.getByText("PRESSING:100")).toBeInTheDocument();
    fireEvent.pointerUp(line, { pointerId: 9 });
    expect(screen.getByText("ACTIVE_CANCEL:100")).toBeInTheDocument();
    expect(screen.getByText("active-cancel-visible")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    expect(screen.getByText("ACTIVE_CANCEL:100")).toBeInTheDocument();
  });

  it("enters EDITING from ACTIVE only when the 300 ms threshold completes", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 10, button: 0, clientX: 10, clientY: 10 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS - 1));
    expect(screen.getByText("PRESSING:100")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByText("EDITING:100")).toBeInTheDocument();
  });

  it("aborts PRESSING after pre-hold movement without changing price or later editing", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 1, button: 0, clientX: 10, clientY: 10 });
    fireEvent.pointerMove(line, { pointerId: 1, clientX: 19, clientY: 10 });
    expect(screen.getByText("PRESSING:100")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS + 1));
    expect(screen.getByText("PRESSING:100")).toBeInTheDocument();
    fireEvent.pointerUp(line, { pointerId: 1 });
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();
    expect(screen.queryByText("active-cancel-visible")).not.toBeInTheDocument();
  });

  it("cancels an ACTIVE order once only after its tap affordance is activated", async () => {
    vi.useFakeTimers();
    const amend = vi.fn(async () => {});
    const cancelOrder = vi.fn(async () => {});
    render(<Harness amend={amend} cancelOrder={cancelOrder} />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 11, button: 0, clientX: 10, clientY: 10 });
    fireEvent.pointerUp(line, { pointerId: 11 });
    expect(cancelOrder).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("cancel"));
    await act(async () => {});
    expect(cancelOrder).toHaveBeenCalledOnce();
    expect(cancelOrder).toHaveBeenCalledWith("order-1");
    expect(amend).not.toHaveBeenCalled();
  });

  it("dismisses the ACTIVE cancel affordance outside without a backend command", () => {
    vi.useFakeTimers();
    const amend = vi.fn(async () => {});
    const cancelOrder = vi.fn(async () => {});
    render(<Harness amend={amend} cancelOrder={cancelOrder} />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 12, button: 0, clientX: 10, clientY: 10 });
    fireEvent.pointerUp(line, { pointerId: 12 });
    expect(screen.getByText("active-cancel-visible")).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByTestId("outside"));
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();
    expect(cancelOrder).not.toHaveBeenCalled();
    expect(amend).not.toHaveBeenCalled();
  });

  it("maps cancel to the authoritative order id and confirm to amend", async () => {
    vi.useFakeTimers();
    const amend = vi.fn(async () => {});
    const cancelOrder = vi.fn(async () => {});
    render(<Harness amend={amend} cancelOrder={cancelOrder} />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 2, button: 0 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    fireEvent.pointerMove(line, { pointerId: 2, clientY: 125 });
    fireEvent.pointerUp(line, { pointerId: 2 });
    expect(screen.getByText("PENDING_CONFIRM:125")).toBeInTheDocument();
    fireEvent.click(screen.getByText("cancel"));
    await act(async () => {});
    expect(amend).not.toHaveBeenCalled();
    expect(cancelOrder).toHaveBeenCalledOnce();
    expect(cancelOrder).toHaveBeenCalledWith("order-1");
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();

    fireEvent.pointerDown(line, { pointerId: 3, button: 0 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    fireEvent.pointerMove(line, { pointerId: 3, clientY: 130 });
    fireEvent.pointerUp(line, { pointerId: 3 });
    fireEvent.click(screen.getByText("confirm"));
    fireEvent.click(screen.getByText("confirm"));
    await act(async () => {});
    expect(amend).toHaveBeenCalledTimes(1);
    expect(amend).toHaveBeenCalledWith("order-1", "130");
  });

  it("dismisses outside without cancel or amend and restores the original projection", () => {
    vi.useFakeTimers();
    const amend = vi.fn(async () => {});
    const cancelOrder = vi.fn(async () => {});
    render(<Harness amend={amend} cancelOrder={cancelOrder} />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 5, button: 0 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    fireEvent.pointerMove(line, { pointerId: 5, clientY: 140 });
    fireEvent.pointerUp(line, { pointerId: 5 });
    expect(screen.getByText("PENDING_CONFIRM:140")).toBeInTheDocument();
    fireEvent.pointerDown(screen.getByTestId("outside"));
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();
    expect(cancelOrder).not.toHaveBeenCalled();
    expect(amend).not.toHaveBeenCalled();
  });

  it("consumes a tap on another active line as current-edit dismissal only", () => {
    vi.useFakeTimers();
    const amend = vi.fn(async () => {});
    const cancelOrder = vi.fn(async () => {});
    const onOtherActive = vi.fn();
    render(<Harness amend={amend} cancelOrder={cancelOrder} onOtherActive={onOtherActive} />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 13, button: 0 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    fireEvent.pointerMove(line, { pointerId: 13, clientY: 140 });
    fireEvent.pointerUp(line, { pointerId: 13 });
    fireEvent.pointerDown(screen.getByTestId("other-active"), { pointerId: 14, button: 0 });
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();
    expect(onOtherActive).not.toHaveBeenCalled();
    expect(cancelOrder).not.toHaveBeenCalled();
    expect(amend).not.toHaveBeenCalled();
  });

  it("consumes a tap on another pending line as current-edit dismissal only", () => {
    vi.useFakeTimers();
    const onOtherPending = vi.fn();
    render(<Harness onOtherPending={onOtherPending} />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 15, button: 0 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    fireEvent.pointerUp(line, { pointerId: 15 });
    fireEvent.pointerDown(screen.getByTestId("other-pending"), { pointerId: 16, button: 0 });
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();
    expect(onOtherPending).not.toHaveBeenCalled();
  });

  it("keeps global candidate controls inside the current edit boundary", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 17, button: 0 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    fireEvent.pointerUp(line, { pointerId: 17 });
    fireEvent.pointerDown(screen.getByText("global-candidate-control"), { pointerId: 18, button: 0 });
    expect(screen.getByText("PENDING_CONFIRM:100")).toBeInTheDocument();
  });

  it("re-grabs and re-drags a pending candidate repeatedly without a backend command", () => {
    vi.useFakeTimers();
    const amend = vi.fn(async () => {});
    const cancelOrder = vi.fn(async () => {});
    render(<Harness amend={amend} cancelOrder={cancelOrder} />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 6, button: 0 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    fireEvent.pointerMove(line, { pointerId: 6, clientY: 125 });
    fireEvent.pointerUp(line, { pointerId: 6 });
    expect(screen.getByText("PENDING_CONFIRM:125")).toBeInTheDocument();

    fireEvent.pointerDown(line, { pointerId: 7, button: 0 });
    expect(screen.getByText("EDITING:125")).toBeInTheDocument();
    fireEvent.pointerMove(line, { pointerId: 7, clientY: 140 });
    fireEvent.pointerUp(line, { pointerId: 7 });
    expect(screen.getByText("PENDING_CONFIRM:140")).toBeInTheDocument();

    fireEvent.pointerDown(line, { pointerId: 8, button: 0 });
    fireEvent.pointerMove(line, { pointerId: 8, clientY: 155 });
    fireEvent.pointerUp(line, { pointerId: 8 });
    expect(screen.getByText("PENDING_CONFIRM:155")).toBeInTheDocument();
    expect(amend).not.toHaveBeenCalled();
    expect(cancelOrder).not.toHaveBeenCalled();
  });

  it("cancels a press on pointer cancellation", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 4, button: 0 });
    fireEvent.pointerCancel(line, { pointerId: 4 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();
  });

  it("confirms normal drafts and the edited active candidate through their canonical callbacks", async () => {
    const confirmDraft = vi.fn(async () => {});
    const confirmEditedActive = vi.fn(async () => {});
    await confirmVisibleLimitCandidates({
      draftIds: ["draft-1"],
      activeCandidate: { orderId: "order-1", candidatePrice: "155" },
      confirmDraft,
      confirmEditedActive,
    });
    expect(confirmDraft).toHaveBeenCalledOnce();
    expect(confirmDraft).toHaveBeenCalledWith("draft-1");
    expect(confirmEditedActive).toHaveBeenCalledOnce();
    expect(confirmEditedActive).toHaveBeenCalledWith({ orderId: "order-1", candidatePrice: "155" });
  });

  it("discards normal drafts and authoritatively cancels the edited active candidate", async () => {
    const dismissDrafts = vi.fn();
    const cancelEditedActive = vi.fn(async () => {});
    await cancelVisibleLimitCandidates({
      draftIds: ["draft-1"],
      activeCandidate: { orderId: "order-1", candidatePrice: "155" },
      dismissDrafts,
      cancelEditedActive,
    });
    expect(dismissDrafts).toHaveBeenCalledOnce();
    expect(cancelEditedActive).toHaveBeenCalledOnce();
    expect(cancelEditedActive).toHaveBeenCalledWith({ orderId: "order-1", candidatePrice: "155" });
  });
});
