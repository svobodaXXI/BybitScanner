import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

it("shows legacy DT/DB review as historical text, never a selectable pattern", () => {
  render(<ChartPanel candles={[]} tickSize={null} editorMode
    signalIdentity="signal-legacy" originalPattern="Rising Wedge"
    savedCorrectedPattern="Double Top/Bottom"
    snapshotRevision={"a".repeat(64)} barsSha256={"b".repeat(64)} />);
  const select = screen.getByRole("combobox", { name: "Правильный паттерн" });
  expect(select).toHaveValue("Rising Wedge");
  expect(within(select).queryByRole("option", { name: /Двойная вершина/ })).toBeNull();
  expect(screen.getByLabelText("Ранее сохранённое исправление")).toHaveTextContent("Double Top/Bottom");
});

it("keeps correction form left and all three quick actions bottom-right", async () => {
  const onShowCurrentEditorChart = vi.fn();
  const onExtendEditorHistory = vi.fn().mockResolvedValue(undefined);
  const view = render(<ChartPanel
    candles={[]} tickSize={null} editorMode
    signalIdentity="signal-test" originalPattern="Rising Wedge"
    snapshotRevision={"a".repeat(64)} barsSha256={"b".repeat(64)}
    onShowCurrentEditorChart={onShowCurrentEditorChart}
    onExtendEditorHistory={onExtendEditorHistory}
  />);
  const selected = screen.getByRole("combobox", { name: "Правильный паттерн" });
  expect(selected).toHaveValue("Rising Wedge");
  expect(within(selected).getByRole("option", { name: "Рупор" })).toHaveValue("Broadening");
  expect(within(selected).queryByRole("option", { name: "Двойная вершина / дно" })).toBeNull();
  expect(screen.getByLabelText("Название исходного сигнала")).toHaveTextContent("Rising Wedge");
  expect(screen.queryByRole("combobox", { name: "Оценка сигнала" })).not.toBeInTheDocument();
  fireEvent.change(selected, { target: { value: "Triangle" } });
  expect(selected).toHaveValue("Triangle");

  const left = view.container.querySelector(".editor-review-fields");
  const bottom = view.container.querySelector(".editor-bottom-actions");
  expect(left).not.toBeNull();
  expect(bottom).not.toBeNull();
  expect(view.container.querySelector(".editor-review-layout")).not.toBeNull();
  expect(within(left as HTMLElement).getAllByRole("combobox").map((element) => element.getAttribute("aria-label"))).toEqual([
    "Правильный паттерн",
  ]);
  expect(within(left as HTMLElement).getByRole("textbox", { name: "Комментарий к исправлению" })).toBeInTheDocument();
  expect(within(left as HTMLElement).getByRole("button", { name: "Передать исправление" })).toBeInTheDocument();
  expect(within(bottom as HTMLElement).getAllByRole("button").map((button) => button.textContent)).toEqual([
    "Показать следующие свечи", "Актуальный график", "Создать новый сигнал",
  ]);
  expect(within(left as HTMLElement).queryByRole("button", { name: "Показать следующие свечи" })).not.toBeInTheDocument();
  fireEvent.click(within(bottom as HTMLElement).getByRole("button", { name: "Показать следующие свечи" }));
  expect(onExtendEditorHistory).toHaveBeenCalledOnce();
  await waitFor(() => expect(within(bottom as HTMLElement).getByRole("button", { name: "Показать следующие свечи" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Актуальный график" }));
  expect(onShowCurrentEditorChart).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Создать новый сигнал" }));
  expect(screen.getByRole("button", { name: "Вернуться к исправлению" })).toBeInTheDocument();
  const newPattern = screen.getByRole("combobox", { name: "Тип нового сигнала" });
  expect(newPattern).toHaveValue("Wedge");
  expect(within(newPattern).getByRole("option", { name: "Рупор" })).toHaveValue("Broadening");
  expect(within(newPattern).queryByRole("option", { name: "Двойная вершина / дно" })).toBeNull();
  expect(screen.getByRole("combobox", { name: "Направление движения графика" })).toBeInTheDocument();
  expect(within(bottom as HTMLElement).queryByRole("button", { name: "Создать новый сигнал" })).toBeNull();
});
