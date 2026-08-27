import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PendingLimitLine } from "./PendingLimitLine";

describe("PendingLimitLine", () => {
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
});
