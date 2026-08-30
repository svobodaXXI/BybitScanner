import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ChartPanel } from "./ChartPanel";

const applyPriceLineOptions = vi.fn();
const createPriceLine = vi.fn(() => ({ applyOptions: applyPriceLineOptions }));
const removePriceLine = vi.fn();

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: {},
  ColorType: { Solid: "Solid" },
  CrosshairMode: { Normal: 0 },
  LineStyle: { Solid: 0 },
  createChart: () => ({
    addSeries: () => ({
      coordinateToPrice: () => 100,
      priceToCoordinate: () => 100,
      setData: vi.fn(),
      applyOptions: vi.fn(),
      createPriceLine,
      removePriceLine,
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

it("creates, updates, clears, and rebinds the authoritative average-entry line", () => {
  const view = render(
    <ChartPanel candles={[]} tickSize={0.5} symbol="BTCUSDT" averageEntryPrice="100" />,
  );
  expect(createPriceLine).toHaveBeenCalledWith(expect.objectContaining({
    price: 100,
    color: "#d7dce2",
    lineStyle: 0,
  }));

  view.rerender(
    <ChartPanel candles={[]} tickSize={0.5} symbol="BTCUSDT" averageEntryPrice="101" />,
  );
  expect(applyPriceLineOptions).toHaveBeenCalledWith({ price: 101 });

  view.rerender(
    <ChartPanel candles={[]} tickSize={0.5} symbol="ETHUSDT" averageEntryPrice="200" />,
  );
  expect(removePriceLine).toHaveBeenCalledTimes(1);
  expect(createPriceLine).toHaveBeenCalledTimes(2);
  expect(createPriceLine).toHaveBeenLastCalledWith(expect.objectContaining({ price: 200 }));

  view.rerender(
    <ChartPanel candles={[]} tickSize={0.5} symbol="ETHUSDT" averageEntryPrice={null} />,
  );
  expect(removePriceLine).toHaveBeenCalledTimes(2);
});
