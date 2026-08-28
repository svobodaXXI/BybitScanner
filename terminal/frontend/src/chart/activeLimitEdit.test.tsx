import { fireEvent, render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ACTIVE_LIMIT_EDIT_HOLD_MS, useActiveLimitEdit } from "./activeLimitEdit";

function Harness({ amend = async () => {} }: { amend?: (orderId: string, price: string) => Promise<void> }) {
  const edit = useActiveLimitEdit({
    priceAtClientY: (clientY) => String(clientY),
    normalizePrice: (price) => price,
    amend,
  });
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
    <button onClick={() => void edit.confirm()}>confirm</button>
    <button onClick={edit.cancel}>cancel</button>
  </>;
}

describe("active Limit edit controller", () => {
  afterEach(() => vi.useRealTimers());

  it("keeps a short press and pre-hold movement inactive", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 1, button: 0 });
    fireEvent.pointerMove(line, { pointerId: 1, clientY: 125 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS - 1));
    fireEvent.pointerUp(line, { pointerId: 1 });
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();
  });

  it("edits locally after 300 ms, cancels without amend, and confirms once with the same order id", async () => {
    vi.useFakeTimers();
    const amend = vi.fn(async () => {});
    render(<Harness amend={amend} />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 2, button: 0 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    fireEvent.pointerMove(line, { pointerId: 2, clientY: 125 });
    fireEvent.pointerUp(line, { pointerId: 2 });
    expect(screen.getByText("PENDING_CONFIRM:125")).toBeInTheDocument();
    fireEvent.click(screen.getByText("cancel"));
    expect(amend).not.toHaveBeenCalled();
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

  it("cancels a press on pointer cancellation", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const line = screen.getByTestId("line");
    fireEvent.pointerDown(line, { pointerId: 4, button: 0 });
    fireEvent.pointerCancel(line, { pointerId: 4 });
    act(() => vi.advanceTimersByTime(ACTIVE_LIMIT_EDIT_HOLD_MS));
    expect(screen.getByText("ACTIVE:100")).toBeInTheDocument();
  });
});
