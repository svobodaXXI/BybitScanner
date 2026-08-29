import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TradingControlButton } from "./useTradingControlActivation";

afterEach(() => {
  vi.useRealTimers();
});

describe("TradingControlButton pointer activation", () => {
  it("fires one touch tap on pointerup and suppresses its compatibility click", () => {
    const onTap = vi.fn();
    render(<TradingControlButton onTap={onTap}>PRICE</TradingControlButton>);
    const button = screen.getByRole("button", { name: "PRICE" });

    fireEvent.pointerDown(button, {
      button: 0,
      pointerId: 2,
      pointerType: "touch",
    });
    fireEvent.pointerUp(button, { pointerId: 2, pointerType: "touch" });
    expect(onTap).toHaveBeenCalledOnce();

    fireEvent.click(button, { detail: 1 });
    expect(onTap).toHaveBeenCalledOnce();
  });

  it("ends a touch hold without producing a tap", () => {
    vi.useFakeTimers();
    const onTap = vi.fn();
    const onHoldStart = vi.fn();
    const onHoldEnd = vi.fn();
    render(
      <TradingControlButton
        holdMs={200}
        onHoldEnd={onHoldEnd}
        onHoldStart={onHoldStart}
        onTap={onTap}
      >
        BUY
      </TradingControlButton>,
    );
    const button = screen.getByRole("button", { name: "BUY" });

    fireEvent.pointerDown(button, {
      button: 0,
      pointerId: 1,
      pointerType: "touch",
    });
    vi.advanceTimersByTime(200);
    expect(onHoldStart).toHaveBeenCalledOnce();

    fireEvent.pointerUp(button, { pointerId: 1, pointerType: "touch" });
    expect(onHoldEnd).toHaveBeenCalledOnce();
    expect(onTap).not.toHaveBeenCalled();
  });
});
