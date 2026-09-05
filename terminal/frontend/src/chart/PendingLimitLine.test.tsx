import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PendingLimitLine } from "./PendingLimitLine";

describe("PendingLimitLine", () => {
  it.each([
    ["submitting", "SUBMITTING…"],
    ["ambiguous", "RECONCILING — DO NOT RETRY"],
  ] as const)("shows LIVE %s and blocks touch and keyboard confirmation", (liveSubmitStatus, label) => {
    const onConfirm = vi.fn();
    render(<PendingLimitLine side="Buy" price="0.1" top={120}
      onDragClientY={vi.fn()} onConfirm={onConfirm} liveSubmitStatus={liveSubmitStatus} />);
    expect(screen.getByRole("status")).toHaveTextContent(label);
    Object.assign(screen.getByRole("slider"), {
      setPointerCapture: vi.fn(), hasPointerCapture: vi.fn(() => false), releasePointerCapture: vi.fn(),
    });
    const confirm = screen.getByRole("button", { name: "Confirm pending Buy Limit" });
    expect(confirm).toBeDisabled();
    fireEvent.pointerDown(confirm, { button: 0, pointerId: 10, pointerType: "touch" });
    fireEvent.pointerUp(confirm, { pointerId: 10, pointerType: "touch" });
    fireEvent.click(confirm, { detail: 0 });
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("renders one pending line and reports drag coordinates", () => {
    const onDragClientY = vi.fn();
    render(
      <PendingLimitLine
        side="Buy"
        price="62965"
        top={120}
        onDragClientY={onDragClientY}
      />,
    );
    const line = screen.getByRole("slider", {
      name: "Pending Buy Limit at 62965",
    });
    Object.assign(line, {
      setPointerCapture: vi.fn(),
      hasPointerCapture: vi.fn(() => true),
      releasePointerCapture: vi.fn(),
    });

    fireEvent.pointerDown(line, { pointerId: 1, clientY: 120 });
    fireEvent.pointerMove(line, { pointerId: 1, clientY: 140 });

    expect(onDragClientY).toHaveBeenCalledWith(140);
    expect(document.querySelectorAll(".pending-limit-line")).toHaveLength(1);
  });

  it("renders no line without a chart coordinate", () => {
    const { container } = render(
      <PendingLimitLine
        side="Sell"
        price="65535"
        top={null}
        onDragClientY={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("keeps the confirmation checkmark on the green action style for Sell", () => {
    render(
      <PendingLimitLine
        side="Sell"
        price="65535"
        top={120}
        onDragClientY={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", {
      name: "Confirm pending Sell Limit",
    })).toHaveClass("pending-limit-confirm");
  });

  it("keeps invalid-volume confirmation disabled and emits no touch activation", () => {
    const onConfirm = vi.fn();
    render(
      <PendingLimitLine
        side="Buy"
        price="0.1"
        top={120}
        onDragClientY={vi.fn()}
        onConfirm={onConfirm}
        confirmDisabled
      />,
    );
    const confirm = screen.getByRole("button", { name: "Confirm pending Buy Limit" });
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm, { detail: 0 });
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("submits one valid touch confirmation and suppresses its compatibility click", () => {
    const onConfirm = vi.fn();
    render(
      <PendingLimitLine
        side="Buy"
        price="0.1"
        top={120}
        onDragClientY={vi.fn()}
        onConfirm={onConfirm}
      />,
    );
    const confirm = screen.getByRole("button", { name: "Confirm pending Buy Limit" });
    fireEvent.pointerDown(confirm, { button: 0, pointerId: 10, pointerType: "touch" });
    fireEvent.pointerUp(confirm, { pointerId: 10, pointerType: "touch" });
    fireEvent.click(confirm, { detail: 0 });
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
