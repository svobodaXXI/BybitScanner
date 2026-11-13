import { fireEvent, render, screen, within } from "@testing-library/react";
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

it("defaults to the Scanner pattern and places chart/new-signal actions last at the right-bottom rail", () => {
  const onShowCurrentEditorChart = vi.fn();
  const view = render(<ChartPanel
    candles={[]} tickSize={null} editorMode
    signalIdentity="signal-test" originalPattern="Rising Wedge"
    snapshotRevision={"a".repeat(64)} barsSha256={"b".repeat(64)}
    onShowCurrentEditorChart={onShowCurrentEditorChart}
  />);
  const selected = screen.getByRole("combobox", { name: "Правильный паттерн" });
  expect(selected).toHaveValue("Rising Wedge");
  expect(screen.getByLabelText("Название исходного сигнала")).toHaveTextContent("Rising Wedge");
  expect(screen.queryByRole("combobox", { name: "Оценка сигнала" })).not.toBeInTheDocument();
  fireEvent.change(selected, { target: { value: "Triangle" } });
  expect(selected).toHaveValue("Triangle");

  const bottom = view.container.querySelector(".editor-bottom-actions");
  expect(bottom).not.toBeNull();
  expect(within(bottom as HTMLElement).getAllByRole("button").map((button) => button.textContent)).toEqual([
    "Актуальный график", "Создать новый сигнал",
  ]);
  fireEvent.click(screen.getByRole("button", { name: "Актуальный график" }));
  expect(onShowCurrentEditorChart).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Создать новый сигнал" }));
  expect(screen.getByRole("button", { name: "Вернуться к исправлению" })).toBeInTheDocument();
  expect(within(bottom as HTMLElement).queryByRole("button", { name: "Создать новый сигнал" })).toBeNull();
});
