import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ChartPanel } from "./ChartPanel";

const seriesSetData = vi.hoisted(() => vi.fn());

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: {},
  ColorType: { Solid: "Solid" },
  CrosshairMode: { Normal: 0 },
  createChart: () => ({
    addSeries: () => ({
      coordinateToPrice: () => 98,
      priceToCoordinate: () => 100,
      setData: seriesSetData,
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

it("previews current candles inside Editor and restores the frozen view without edits", () => {
  const source = [
    { time: "2026-11-01T00:00:00Z", open: 10, high: 12, low: 9, close: 11 },
    { time: "2026-11-01T00:05:00Z", open: 11, high: 13, low: 10, close: 12 },
  ];
  const current = [
    { time: "2026-11-11T00:00:00Z", open: 30, high: 32, low: 29, close: 31 },
    { time: "2026-11-11T00:05:00Z", open: 31, high: 34, low: 30, close: 33 },
  ];
  seriesSetData.mockClear();
  render(
    <ChartPanel candles={source} currentCandles={current} tickSize={null}
      editorMode signalIdentity="source-original:abc" symbol="ICNTUSDT" timeframe="5m" />,
  );
  expect(seriesSetData.mock.lastCall?.[0].at(-1).close).toBe(12);
  expect(screen.getByRole("button", { name: "Показать следующие свечи" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Показать актуальный график" }));
  expect(seriesSetData.mock.lastCall?.[0].at(-1).close).toBe(33);
  expect(screen.getByText(/Текущие рыночные свечи ICNTUSDT/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Показать следующие свечи" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Вернуться к сигналу" }));
  expect(seriesSetData.mock.lastCall?.[0].at(-1).close).toBe(12);
  expect(screen.getByRole("button", { name: "Показать следующие свечи" })).toBeInTheDocument();
});

it("does not offer current chart without matching market candles", () => {
  render(<ChartPanel candles={[]} tickSize={null}
    editorMode signalIdentity="source-original:abc" />);
  expect(screen.getByRole("button", { name: "Показать актуальный график" })).toBeDisabled();
});
