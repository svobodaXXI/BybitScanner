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

it("restores Telegram source lines locally with Undo but never invokes review save", () => {
  const onSaveGeometryReview = vi.fn();
  const source = {
    id: "source-ray", type: "ray" as const,
    anchors: [{ logical: 1, price: 100 }, { logical: 2, price: 110 }],
    style: { color: "#8195aa", lineWidth: 1.5 }, locked: true, hidden: false,
  };
  const corrected = {
    ...source, id: "editable:source-ray",
    anchors: [{ logical: 1, price: 100 }, { logical: 2, price: 120 }],
    style: { color: "#e0b45b", lineWidth: 1.5 }, locked: false,
  };
  const view = render(<ChartPanel candles={[]} tickSize={null} editorMode
    signalIdentity="restore-source-test" originalPattern="Rising Wedge"
    snapshotRevision={"a".repeat(64)} barsSha256={"b".repeat(64)}
    referenceDrawings={[source]} editableSeedDrawings={[corrected]}
    onSaveGeometryReview={onSaveGeometryReview} />);
  const restore = screen.getByRole("button", { name: "Вернуть исходную геометрию" });
  expect(view.container.querySelector(".editor-review-layout > .editor-restore-original")).toBe(restore);
  expect(screen.getByRole("button", { name: "Undo drawing" })).toBeDisabled();
  fireEvent.click(restore);
  expect(onSaveGeometryReview).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Undo drawing" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Undo drawing" }));
  expect(screen.getByRole("button", { name: "Undo drawing" })).toBeDisabled();
  expect(onSaveGeometryReview).not.toHaveBeenCalled();
});


it("blocks correction submission until the next-candle request finishes, then saves the latest context once", async () => {
  let finishExtension!: () => void;
  const extension = new Promise<void>((resolve) => { finishExtension = resolve; });
  const onExtendEditorHistory = vi.fn(() => extension);
  const onSaveGeometryReview = vi.fn().mockResolvedValue({ reviewId: "saved-review", label: "GEOMETRY_CORRECTED" });
  const source = {
    id: "source-ray", type: "ray" as const,
    anchors: [{ logical: 0, price: 100 }, { logical: 1, price: 110 }],
    style: { color: "#8195aa", lineWidth: 1.5 }, locked: true, hidden: false,
  };
  const corrected = {
    ...source, id: "editable:source-ray", locked: false,
    anchors: [{ logical: 0, price: 100 }, { logical: 1, price: 112 }],
  };
  const candles = ["2026-11-22T07:00:00Z", "2026-11-22T07:05:00Z"].map(time =>
    ({ time, open: 100, high: 115, low: 98, close: 105 }));
  const props = {
    candles, tickSize: null, editorMode: true, signalIdentity: "extension-review-test",
    originalPattern: "Rising Wedge", snapshotRevision: "a".repeat(64),
    barsSha256: "b".repeat(64), referenceDrawings: [source], editableSeedDrawings: [corrected],
    onExtendEditorHistory, onSaveGeometryReview,
  };
  const view = render(<ChartPanel {...props} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Правильный паттерн" }), { target: { value: "Falling Wedge" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Комментарий к исправлению" }), { target: { value: "Уточнение границы" } });
  const save = screen.getByRole("button", { name: "Передать исправление" });
  expect(save).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Показать следующие свечи" }));
  expect(onExtendEditorHistory).toHaveBeenCalledOnce();
  expect(save).toBeDisabled();
  fireEvent.click(save);
  expect(onSaveGeometryReview).not.toHaveBeenCalled();
  const context = { asOfMs: Date.parse("2026-11-22T07:10:00Z"), barsSha256: "c".repeat(64) };
  view.rerender(<ChartPanel {...props} retrospectiveContext={context} />);
  finishExtension();
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.click(save);
  await waitFor(() => expect(onSaveGeometryReview).toHaveBeenCalledOnce());
  expect(onSaveGeometryReview).toHaveBeenCalledWith(expect.objectContaining({
    signal_id: props.signalIdentity, label: "GEOMETRY_CORRECTED", corrected_pattern: "Falling Wedge",
    note: "Уточнение границы", context_as_of_ms: context.asOfMs, context_bars_sha256: context.barsSha256,
    corrected_boundaries: [{ id: "source-ray", type: "ray", anchors: [
      { bar_open_time_ms: Date.parse(candles[0].time), price: 100 },
      { bar_open_time_ms: Date.parse(candles[1].time), price: 112 },
    ] }],
  }));
  expect(await screen.findByText("Исправление сохранено")).toBeInTheDocument();
});
