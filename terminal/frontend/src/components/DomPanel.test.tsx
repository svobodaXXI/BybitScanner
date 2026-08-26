import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { NormalizedOrderBook } from "../contracts/marketData";
import { DomPanel } from "./DomPanel";

const book: NormalizedOrderBook = {
  symbol: "ONGUSDT",
  bids: [{ price: 0.169, quantity: 10 }],
  asks: [{ price: 0.16901, quantity: 12 }],
  health: "READY",
  receivedAt: "now",
  availableDepth: 1,
};

function renderDom(onCompressionChange = vi.fn()) {
  render(
    <DomPanel
      book={book}
      centerPrice={0.169}
      onCenterPriceChange={vi.fn()}
      ownOrders={[]}
      compression={3}
      onCompressionChange={onCompressionChange}
    />,
  );
  return onCompressionChange;
}

describe("DOM compression editor", () => {
  it("selects the current value so typing replaces 3 with 10", () => {
    const onCompressionChange = renderDom();
    expect(screen.getByRole("button", { name: "DOM compression" })).toHaveTextContent("x3");

    fireEvent.click(screen.getByRole("button", { name: "DOM compression" }));
    const input = screen.getByRole("textbox", {
      name: "DOM compression",
    }) as HTMLInputElement;
    fireEvent.focus(input);
    expect(input.value).toBe("3");
    expect(input.selectionStart).toBe(0);
    expect(input.selectionEnd).toBe(1);

    fireEvent.change(input, { target: { value: "10" } });
    fireEvent.blur(input);
    expect(onCompressionChange).toHaveBeenCalledOnce();
    expect(onCompressionChange).toHaveBeenCalledWith(10);
  });

  it("preserves the existing validation and rejects values above 100", () => {
    const onCompressionChange = renderDom();
    fireEvent.click(screen.getByRole("button", { name: "DOM compression" }));
    const input = screen.getByRole("textbox", { name: "DOM compression" });
    fireEvent.change(input, { target: { value: "101" } });
    fireEvent.blur(input);
    expect(onCompressionChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "DOM compression" })).toHaveTextContent("x3");
  });
});
