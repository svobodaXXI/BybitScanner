import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ChartPanel } from "./ChartPanel";

const coordinateToPrice = vi.fn(() => 100.5);

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: {},
  ColorType: { Solid: "Solid" },
  CrosshairMode: { Normal: 0 },
  createChart: () => ({
    addSeries: () => ({
      coordinateToPrice,
      priceToCoordinate: () => 100,
      setData: vi.fn(),
      applyOptions: vi.fn(),
    }),
    timeScale: () => ({
      subscribeVisibleLogicalRangeChange: vi.fn(),
      unsubscribeVisibleLogicalRangeChange: vi.fn(),
      getVisibleLogicalRange: () => ({ from: 0, to: 1 }),
      setVisibleLogicalRange: vi.fn(),
      getScrollPosition: () => 0,
      scrollToPosition: vi.fn(),
      coordinateToLogical: () => 0,
    }),
    priceScale: () => ({
      width: () => 64,
      getVisibleRange: () => ({ from: 90, to: 110 }),
    }),
    remove: vi.fn(),
    clearCrosshairPosition: vi.fn(),
  }),
}));

it("creates a fast Limit from the first non-primary chart touch", () => {
  const onFastLimitPriceSelect = vi.fn();
  coordinateToPrice.mockReturnValueOnce(null);
  render(
    <ChartPanel
      candles={[]}
      tickSize={0.5}
      fastLimitActive
      onFastLimitPriceSelect={onFastLimitPriceSelect}
    />,
  );
  const chart = screen.getByRole("application", {
    name: "Interactive market chart",
  });
  Object.defineProperty(chart.firstElementChild, "getBoundingClientRect", {
    value: () => ({ left: 0, top: 0 }),
  });
  Object.defineProperty(chart.firstElementChild, "clientHeight", {
    value: 200,
  });

  fireEvent.touchStart(chart, {
    changedTouches: [{ identifier: 2, clientX: 50, clientY: 80 }],
    touches: [{ identifier: 1 }, { identifier: 2, clientX: 50, clientY: 80 }],
  });

  expect(onFastLimitPriceSelect).toHaveBeenCalledOnce();
  expect(Number(onFastLimitPriceSelect.mock.calls[0][0])).toBeCloseTo(100.588);
});

it("positions confirm-all popup directly above the shared green button", () => {
  render(
    <ChartPanel
      candles={[]}
      tickSize={0.5}
      pendingLimitDrafts={[{
        draftId: "draft-1",
        symbol: "BTCUSDT",
        side: "Buy",
        origin: "chart-fast",
        volume: { unit: "usdt", amount: "250" },
        sizingReferencePrice: "100",
        price: "99",
        authoritativeTickSize: "0.5",
        status: "draft",
        clientActionId: null,
        rejectionReason: null,
      }]}
    />,
  );

  fireEvent.click(screen.getByRole("button", {
    name: "Confirm all pending Limit drafts",
  }));
  const card = screen.getByText("Confirm all pending limits?").parentElement!;
  expect(card.parentElement).toHaveClass("submit-all");
  expect(card).toHaveStyle({
    position: "absolute",
    right: "105.6px",
    bottom: "54.4px",
  });
});
