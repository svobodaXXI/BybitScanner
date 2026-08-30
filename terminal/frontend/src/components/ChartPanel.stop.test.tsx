import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ChartPanel } from "./ChartPanel";

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: {},
  ColorType: { Solid: "Solid" },
  CrosshairMode: { Normal: 0 },
  createChart: () => ({
    addSeries: () => ({
      coordinateToPrice: () => 98,
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
      setAutoScale: vi.fn(),
      setVisibleRange: vi.fn(),
    }),
    remove: vi.fn(),
    clearCrosshairPosition: vi.fn(),
  }),
}));

it("renders authoritative solid STOP and local dashed edit through chart coordinates", () => {
  const view = render(
    <ChartPanel candles={[]} tickSize={0.5} authoritativeStopPrice="98" />,
  );
  expect(screen.getByLabelText("Active STOP at 98")).toHaveClass("active");

  view.rerender(
    <ChartPanel
      candles={[]}
      tickSize={0.5}
      authoritativeStopPrice="98"
      stopDraft={{
        symbol: "BTCUSDT",
        mode: "EDIT",
        price: "97",
        originalPrice: "98",
        status: "editing",
      }}
    />,
  );
  expect(screen.getByRole("slider", { name: "Pending STOP at 97" })).toHaveClass("draft");
  expect(screen.queryByLabelText("Active STOP at 98")).toBeNull();
});

it("renders authoritative TAKE and replaces it with only the local pending edit", () => {
  const view = render(
    <ChartPanel candles={[]} tickSize={0.5} authoritativeTakePrice="103" />,
  );
  expect(screen.getByLabelText("Active TAKE at 103")).toHaveClass("take", "active");
  view.rerender(
    <ChartPanel candles={[]} tickSize={0.5} authoritativeTakePrice="103" takeDraft={{
      symbol: "BTCUSDT", mode: "EDIT", price: "104", originalPrice: "103", status: "editing",
    }} />,
  );
  expect(screen.getByRole("slider", { name: "Pending TAKE at 104" })).toHaveClass("draft");
  expect(screen.queryByLabelText("Active TAKE at 103")).toBeNull();
});
