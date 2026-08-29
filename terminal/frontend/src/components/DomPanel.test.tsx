import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { NormalizedOrderBook } from "../contracts/marketData";
import { DomPanel } from "./DomPanel";

const book: NormalizedOrderBook = {
  symbol: "ONGUSDT",
  bids: [
    { price: 0.169, quantity: 10 },
    { price: 0.16899, quantity: 8 },
  ],
  asks: [
    { price: 0.16901, quantity: 12 },
    { price: 0.16902, quantity: 7 },
  ],
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
  it("uses the reserved top track for explicit CENTER and compression controls", () => {
    const { container } = render(
      <DomPanel
        book={book}
        centerPrice={0.169}
        onCenterPriceChange={vi.fn()}
        ownOrders={[]}
        compression={3}
        onCompressionChange={vi.fn()}
      />,
    );
    const panel = container.querySelector(".dom-panel")!;
    const header = panel.firstElementChild;
    expect(header).toHaveClass("dom-control-header");
    expect(header).toContainElement(screen.getByRole("button", { name: "CENTER" }));
    expect(header).toContainElement(screen.getByRole("button", { name: "DOM compression" }));
    expect(header?.nextElementSibling).toHaveClass("dom-ladder-viewport");
  });

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

describe("DOM responsive ladder height", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses an independently constrained viewport and follows its height", () => {
    let resize: ResizeObserverCallback = () => {};
    let observedElement: Element | null = null;
    class ResizeObserverMock {
      constructor(callback: ResizeObserverCallback) {
        resize = callback;
      }
      observe(element: Element) {
        observedElement = element;
      }
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
    const onViewportGeometryChange = vi.fn();
    const { container } = render(
      <DomPanel
        book={book}
        centerPrice={0.169}
        onCenterPriceChange={vi.fn()}
        ownOrders={[]}
        compression={3}
        onCompressionChange={vi.fn()}
        onViewportGeometryChange={onViewportGeometryChange}
      />,
    );
    const viewport = container.querySelector(".dom-ladder-viewport")!;
    const ladder = container.querySelector(".dom-ladder")!;
    expect(observedElement).toBe(viewport);
    expect(observedElement).not.toBe(ladder);
    const viewportHeight = 544;
    act(() => {
      resize([{ contentRect: { height: viewportHeight } } as ResizeObserverEntry], {} as ResizeObserver);
    });
    expect(onViewportGeometryChange).toHaveBeenLastCalledWith({
      visibleRows: 25,
      rowHeightPx: 21.76,
      viewportHeightPx: viewportHeight,
    });
    const rows = ladder.querySelectorAll(".dom-row");
    expect(rows).toHaveLength(25);
    const effectiveRowHeight = 21.76;
    const firstRowTop = 0;
    const lastRowBottom = firstRowTop + rows.length * effectiveRowHeight;
    expect(firstRowTop).toBe(0);
    expect(lastRowBottom).toBeCloseTo(viewportHeight, 10);
    expect(viewport.getAttribute("style")).toContain("--dom-row-height: 21.76px");
    act(() => {
      resize([{ contentRect: { height: 500 } } as ResizeObserverEntry], {} as ResizeObserver);
    });
    expect(onViewportGeometryChange).toHaveBeenLastCalledWith({
      visibleRows: 23,
      rowHeightPx: 500 / 23,
      viewportHeightPx: 500,
    });
    expect(ladder.querySelectorAll(".dom-row")).toHaveLength(23);
    expect(23 * (500 / 23)).toBeCloseTo(500, 10);
    expect(observedElement).toBe(viewport);
  });
});

describe("DOM fast-Limit row activation", () => {
  it("renders every current-row own order as a concrete cancel dot", () => {
    const onOwnOrderCancel = vi.fn();
    render(
      <DomPanel
        book={book}
        centerPrice={0.169}
        onCenterPriceChange={vi.fn()}
        ownOrders={[
          { id: "limit-1", price: 0.16899, notionalUsdt: 250, side: "BUY" },
          { id: "limit-2", price: 0.16899, notionalUsdt: 125, side: "BUY" },
        ]}
        compression={3}
        onCompressionChange={vi.fn()}
        onOwnOrderCancel={onOwnOrderCancel}
      />,
    );
    const first = screen.getByRole("button", { name: "Cancel Limit limit-1" });
    const second = screen.getByRole("button", { name: "Cancel Limit limit-2" });
    expect(first.closest(".dom-row")).toBe(second.closest(".dom-row"));
    expect(first.closest(".order-dots")).not.toBeNull();
    fireEvent.click(second);
    expect(onOwnOrderCancel).toHaveBeenCalledWith("limit-2");
  });

  it("selects the same level from price or size and keeps own-order dots cancel-only", () => {
    const onFastLimitPriceSelect = vi.fn();
    const onOwnOrderCancel = vi.fn();
    const { container } = render(
      <DomPanel
        book={book}
        centerPrice={0.169}
        onCenterPriceChange={vi.fn()}
        ownOrders={[
          {
            id: "limit-1",
            price: 0.16899,
            notionalUsdt: 250,
            side: "BUY",
          },
        ]}
        compression={3}
        onCompressionChange={vi.fn()}
        fastLimitActive
        onFastLimitPriceSelect={onFastLimitPriceSelect}
        onOwnOrderCancel={onOwnOrderCancel}
      />,
    );

    const price = screen.getByRole("button", { name: "0.16899" });
    const row = price.closest(".dom-row");
    const size = row?.querySelector(".dom-size");
    expect(size).not.toBeNull();

    fireEvent.pointerDown(price, {
      button: 0,
      pointerId: 2,
      pointerType: "touch",
    });
    fireEvent.pointerUp(price, { pointerId: 2, pointerType: "touch" });
    expect(onFastLimitPriceSelect).toHaveBeenCalledOnce();
    expect(onFastLimitPriceSelect).toHaveBeenLastCalledWith("0.16899");

    onFastLimitPriceSelect.mockClear();
    fireEvent.pointerDown(size!, {
      button: 0,
      clientY: 100,
      pointerId: 3,
      pointerType: "touch",
    });
    fireEvent.pointerUp(size!, {
      clientY: 100,
      pointerId: 3,
      pointerType: "touch",
    });
    expect(onFastLimitPriceSelect).toHaveBeenCalledOnce();
    expect(onFastLimitPriceSelect).toHaveBeenLastCalledWith("0.16899");

    onFastLimitPriceSelect.mockClear();
    fireEvent.click(
      container.querySelector('button[aria-label="Cancel Limit limit-1"]')!,
    );
    expect(onOwnOrderCancel).toHaveBeenCalledOnce();
    expect(onOwnOrderCancel).toHaveBeenCalledWith("limit-1");
    expect(onFastLimitPriceSelect).not.toHaveBeenCalled();
  });
});
