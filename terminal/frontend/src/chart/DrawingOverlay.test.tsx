import { fireEvent, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fibonacciPrices, rulerMeasurement, type DrawingObject } from "./drawingModel";
import { DrawingOverlay } from "./DrawingOverlay";

const coordinates = {
  logicalToX: (value: number) => value,
  xToLogical: (value: number) => value,
  priceToY: (value: number) => value,
  yToPrice: (value: number) => value,
};

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  Object.defineProperty(HTMLCanvasElement.prototype, "setPointerCapture", {
    configurable: true,
    value: vi.fn(),
  });
});

function overlayProps(overrides: Record<string, unknown> = {}) {
  return {
    drawings: [] as DrawingObject[],
    selectedId: null,
    tool: "trend" as const,
    magnet: false,
    candles: [],
    coordinates,
    onCommit: vi.fn(),
    onSelect: vi.fn(),
    onDrawingGesture: vi.fn(),
    onDrawingComplete: vi.fn(),
    ...overrides,
  };
}

describe("drawing interaction state", () => {
  it("creates a two-anchor ray and completes one-shot on the next outside tap", () => {
    let drawings: DrawingObject[] = [];
    const onSelect = vi.fn();
    const onDrawingComplete = vi.fn();
    const onCommit = vi.fn((next: DrawingObject[]) => {
      drawings = next;
    });
    const props = overlayProps({
      tool: "ray",
      onCommit,
      onSelect,
      onDrawingComplete,
    });
    const { container, rerender } = render(<DrawingOverlay {...props} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 20, pointerId: 1 });
    expect(drawings).toHaveLength(1);
    expect(onSelect).toHaveBeenCalledWith(drawings[0].id);
    expect(onDrawingComplete).not.toHaveBeenCalled();

    rerender(
      <DrawingOverlay
        {...props}
        drawings={drawings}
        selectedId={drawings[0].id}
      />,
    );
    fireEvent.pointerMove(canvas, { clientX: 30, clientY: 40, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    fireEvent.pointerDown(canvas, { clientX: 100, clientY: 100, pointerId: 2 });
    expect(onDrawingComplete).toHaveBeenCalledOnce();
    expect(drawings[0].type).toBe("ray");
    expect(drawings[0].anchors).toEqual([
      { logical: 10, price: 20 },
      { logical: 100, price: 100 },
    ]);
  });

  it("completes a one-anchor drawing after its first tap", () => {
    const onDrawingComplete = vi.fn();
    const { container } = render(
      <DrawingOverlay
        {...overlayProps({ tool: "horizontal", onDrawingComplete })}
      />,
    );
    fireEvent.pointerDown(container.querySelector("canvas") as HTMLCanvasElement, {
      clientX: 10,
      clientY: 20,
      pointerId: 1,
    });
    expect(onDrawingComplete).toHaveBeenCalledOnce();
  });

  it("places both Ruler anchors through drag-release with live measurement", () => {
    let drawings: DrawingObject[] = [];
    const onCommit = vi.fn((next: DrawingObject[]) => {
      drawings = next;
    });
    const onSelect = vi.fn();
    const onDrawingComplete = vi.fn();
    const context = {
      setTransform: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fill: vi.fn(),
      fillText: vi.fn(), arc: vi.fn(), save: vi.fn(), restore: vi.fn(),
      setLineDash: vi.fn(),
    };
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(context as never);
    const props = overlayProps({ tool: "ruler", onCommit, onSelect, onDrawingComplete });
    const { container } = render(<DrawingOverlay {...props} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 100, pointerId: 1 });
    expect(context.setLineDash).toHaveBeenCalledWith([5, 4]);
    fireEvent.pointerMove(canvas, { clientX: 20, clientY: 110, pointerId: 1 });
    expect(context.moveTo).toHaveBeenCalledWith(0, 110);
    context.setLineDash.mockClear();
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(context.setLineDash).not.toHaveBeenCalled();
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.pointerDown(canvas, { clientX: 30, clientY: 120, pointerId: 2 });
    expect(context.setLineDash).toHaveBeenCalledWith([5, 4]);
    fireEvent.pointerMove(canvas, { clientX: 40, clientY: 130, pointerId: 2 });
    expect(context.moveTo).toHaveBeenCalledWith(0, 130);
    expect(context.fillText).toHaveBeenCalledWith(
      "+18.18% · +20.0000 · 20 bars · 1h40m", 46, 122,
    );
    expect(onCommit).not.toHaveBeenCalled();
    context.setLineDash.mockClear();
    fireEvent.pointerUp(canvas, { pointerId: 2 });
    expect(context.setLineDash).not.toHaveBeenCalled();

    expect(drawings[0]).toMatchObject({
      type: "ruler",
      anchors: [
        { logical: 20, price: 110 },
        { logical: 40, price: 130 },
      ],
    });
    expect(onSelect).toHaveBeenLastCalledWith(drawings[0].id);
    expect(onDrawingComplete).toHaveBeenCalledOnce();
  });

  it("edits either endpoint of an active completed Ruler", () => {
    let drawings: DrawingObject[] = [{
      id: "ruler-1", type: "ruler",
      anchors: [{ logical: 10, price: 100 }, { logical: 30, price: 120 }],
      style: { color: "#fff", lineWidth: 1 }, locked: false, hidden: false,
    }];
    const context = {
      setTransform: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fill: vi.fn(),
      fillText: vi.fn(), arc: vi.fn(), save: vi.fn(), restore: vi.fn(),
      setLineDash: vi.fn(),
    };
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(context as never);
    const onCommit = vi.fn((next: DrawingObject[]) => { drawings = next; });
    const props = overlayProps({ drawings, selectedId: "ruler-1", tool: "select", onCommit });
    const { container, rerender } = render(<DrawingOverlay {...props} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(canvas, { clientX: 15, clientY: 105, pointerId: 1 });
    expect(context.moveTo).toHaveBeenCalledWith(0, 105);
    context.setLineDash.mockClear();
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(context.setLineDash).not.toHaveBeenCalled();
    expect(drawings[0].anchors).toEqual([
      { logical: 15, price: 105 }, { logical: 30, price: 120 },
    ]);
    rerender(<DrawingOverlay {...props} drawings={drawings} />);
    fireEvent.pointerDown(canvas, { clientX: 30, clientY: 120, pointerId: 2 });
    fireEvent.pointerMove(canvas, { clientX: 35, clientY: 125, pointerId: 2 });
    expect(context.moveTo).toHaveBeenCalledWith(0, 125);
    fireEvent.pointerUp(canvas, { pointerId: 2 });
    expect(drawings[0].anchors).toEqual([
      { logical: 15, price: 105 }, { logical: 35, price: 125 },
    ]);
    expect(rulerMeasurement(drawings[0].anchors[0], drawings[0].anchors[1]).priceDelta)
      .toBe(20);
  });

  it("fixes, rigidly moves, then dismisses a temporary Ruler on outside taps", () => {
    let drawings: DrawingObject[] = [{
      id: "ruler-1", type: "ruler",
      anchors: [{ logical: 10, price: 100 }, { logical: 30, price: 120 }],
      style: { color: "#fff", lineWidth: 1 }, locked: false, hidden: false,
    }];
    const context = {
      setTransform: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fill: vi.fn(),
      fillText: vi.fn(), arc: vi.fn(), save: vi.fn(), restore: vi.fn(),
      setLineDash: vi.fn(),
    };
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(context as never);
    const onCommit = vi.fn((next: DrawingObject[]) => { drawings = next; });
    const onSelect = vi.fn();
    const props = overlayProps({ drawings, selectedId: "ruler-1", tool: "select", onCommit, onSelect });
    const { container, rerender } = render(<DrawingOverlay {...props} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 200, clientY: 200, pointerId: 1 });
    expect(drawings[0].locked).toBe(true);
    expect(drawings).toHaveLength(1);
    rerender(<DrawingOverlay {...props} drawings={drawings} selectedId={null} />);
    context.setLineDash.mockClear();
    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 100, pointerId: 2 });
    fireEvent.pointerMove(canvas, { clientX: 20, clientY: 110, pointerId: 2 });
    fireEvent.pointerUp(canvas, { pointerId: 2 });
    expect(context.setLineDash).not.toHaveBeenCalled();
    expect(drawings[0].anchors).toEqual([
      { logical: 20, price: 110 }, { logical: 40, price: 130 },
    ]);
    expect(drawings[0].anchors[1].price - drawings[0].anchors[0].price).toBe(20);
    expect(rulerMeasurement(drawings[0].anchors[0], drawings[0].anchors[1]).percentDelta)
      .toBeGreaterThan(0);
    expect(drawings).toHaveLength(1);
    rerender(<DrawingOverlay {...props} drawings={drawings} selectedId={null} />);
    fireEvent.pointerDown(canvas, { clientX: 200, clientY: 200, pointerId: 3 });
    expect(drawings).toHaveLength(0);
  });

  it("discards an incomplete one-anchor Ruler on tool change", () => {
    const onCommit = vi.fn();
    const onSelect = vi.fn();
    const props = overlayProps({ tool: "ruler", onCommit, onSelect });
    const { container, rerender } = render(<DrawingOverlay {...props} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(canvas, { clientX: 20, clientY: 110, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    const draftId = onSelect.mock.calls.at(-1)?.[0] as string;
    rerender(<DrawingOverlay {...props} selectedId={draftId} />);
    rerender(<DrawingOverlay {...props} selectedId={draftId} tool="select" />);
    expect(onCommit).not.toHaveBeenCalled();
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("defines both Fibonacci anchors through drag-release gestures in corrected order", () => {
    let drawings: DrawingObject[] = [];
    const onCommit = vi.fn((next: DrawingObject[]) => {
      drawings = next;
    });
    const onDrawingComplete = vi.fn();
    const onSelect = vi.fn();
    const props = overlayProps({ tool: "fibonacci", onCommit, onDrawingComplete, onSelect });
    const { container } = render(<DrawingOverlay {...props} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 100, pointerId: 1 });
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.pointerMove(canvas, { clientX: 20, clientY: 110, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(onCommit).not.toHaveBeenCalled();
    expect(onDrawingComplete).not.toHaveBeenCalled();

    fireEvent.pointerDown(canvas, { clientX: 50, clientY: 140, pointerId: 2 });
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.pointerMove(canvas, { clientX: 60, clientY: 150, pointerId: 2 });
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.pointerUp(canvas, { pointerId: 2 });
    expect(drawings[0]).toMatchObject({
      type: "fibonacci",
      anchors: [
        { logical: 60, price: 150 },
        { logical: 20, price: 110 },
      ],
    });
    expect(fibonacciPrices(drawings[0].anchors[0].price, drawings[0].anchors[1].price))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({ level: 0, price: 150 }),
        expect.objectContaining({ level: 1, price: 110 }),
      ]));
    expect(onSelect).toHaveBeenLastCalledWith(drawings[0].id);
    expect(onDrawingComplete).toHaveBeenCalledOnce();
  });

  it("renders no grid after the first release, then previews the full grid during second drag", () => {
    const context = {
      setTransform: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fill: vi.fn(),
      fillRect: vi.fn(), fillText: vi.fn(), arc: vi.fn(), save: vi.fn(),
      restore: vi.fn(), setLineDash: vi.fn(),
    };
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(context as never);
    const { container } = render(
      <DrawingOverlay {...overlayProps({ tool: "fibonacci" })} />,
    );
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(canvas, { clientX: 20, clientY: 110, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(context.fillRect).not.toHaveBeenCalled();
    context.fillRect.mockClear();
    fireEvent.pointerDown(canvas, { clientX: 50, clientY: 140, pointerId: 2 });
    fireEvent.pointerMove(canvas, { clientX: 60, clientY: 150, pointerId: 2 });
    expect(context.fillRect).toHaveBeenCalled();
    expect(context.fillText).toHaveBeenCalled();
  });

  it("discards an unfinished first-anchor draft on tool change", () => {
    const onCommit = vi.fn();
    const onSelect = vi.fn();
    const props = overlayProps({ tool: "fibonacci", onCommit, onSelect });
    const { container, rerender } = render(<DrawingOverlay {...props} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(canvas, { clientX: 18, clientY: 108, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    const draftId = onSelect.mock.calls.at(-1)?.[0] as string;
    rerender(<DrawingOverlay {...props} selectedId={draftId} />);
    rerender(<DrawingOverlay {...props} selectedId={draftId} tool="trend" />);
    expect(onSelect).toHaveBeenLastCalledWith(null);
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("renders the temporary Fibonacci anchor guide without persisting it", () => {
    const context = {
      setTransform: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fill: vi.fn(),
      arc: vi.fn(), save: vi.fn(), restore: vi.fn(), setLineDash: vi.fn(),
    };
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(context as never);
    const onCommit = vi.fn();
    const { container } = render(
      <DrawingOverlay {...overlayProps({ tool: "fibonacci", onCommit })} />,
    );
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 10, clientY: 100, pointerId: 1 });
    expect(context.setLineDash).toHaveBeenCalledWith([5, 4]);
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("activates an inactive Fibonacci from its visual region without mutating it", () => {
    const drawing: DrawingObject = {
      id: "fib-1",
      type: "fibonacci", anchors: [{ logical: 50, price: 140 }, { logical: 20, price: 110 }],
      style: { color: "#fff", lineWidth: 1 },
      locked: false, hidden: false,
    };
    const onCommit = vi.fn();
    const onSelect = vi.fn();
    const { container } = render(
      <DrawingOverlay
        {...overlayProps({ drawings: [drawing], tool: "select", onCommit, onSelect })}
      />,
    );
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;
    fireEvent.pointerDown(canvas, { clientX: 40, clientY: 80, pointerId: 1 });
    fireEvent.pointerMove(canvas, { clientX: 70, clientY: 90, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(onSelect).toHaveBeenCalledWith("fib-1");
    expect(onCommit).not.toHaveBeenCalled();
  });

  it("keeps Fib band tolerance small while retaining local label hits", () => {
    const drawing: DrawingObject = {
      id: "fib-1", type: "fibonacci",
      anchors: [{ logical: 50, price: 140 }, { logical: 20, price: 110 }],
      style: { color: "#fff", lineWidth: 1 }, locked: false, hidden: false,
    };
    const onSelect = vi.fn();
    const { container } = render(
      <DrawingOverlay {...overlayProps({ drawings: [drawing], tool: "select", onSelect })} />,
    );
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 62, clientY: 75, pointerId: 1 });
    expect(onSelect).toHaveBeenLastCalledWith("fib-1");
    fireEvent.pointerDown(canvas, { clientX: 63, clientY: 75, pointerId: 2 });
    expect(onSelect).toHaveBeenLastCalledWith(null);
    fireEvent.pointerDown(canvas, { clientX: 75, clientY: 140, pointerId: 3 });
    expect(onSelect).toHaveBeenLastCalledWith("fib-1");
    fireEvent.pointerDown(canvas, { clientX: 140, clientY: 75, pointerId: 4 });
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("edits completed Fibonacci anchors only after activation and shows the guide", () => {
    const context = {
      setTransform: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fill: vi.fn(),
      fillRect: vi.fn(), fillText: vi.fn(), arc: vi.fn(), save: vi.fn(),
      restore: vi.fn(), setLineDash: vi.fn(),
    };
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(context as never);
    const drawing: DrawingObject = {
      id: "fib-1", type: "fibonacci",
      anchors: [{ logical: 50, price: 140 }, { logical: 20, price: 110 }],
      style: { color: "#fff", lineWidth: 1 }, locked: false, hidden: false,
    };
    const onCommit = vi.fn();
    const onSelect = vi.fn();
    const props = overlayProps({ drawings: [drawing], tool: "select", onCommit, onSelect });
    const { container, rerender } = render(<DrawingOverlay {...props} />);
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;

    fireEvent.pointerDown(canvas, { clientX: 50, clientY: 140, pointerId: 1 });
    fireEvent.pointerMove(canvas, { clientX: 60, clientY: 150, pointerId: 1 });
    fireEvent.pointerUp(canvas, { pointerId: 1 });
    expect(onCommit).not.toHaveBeenCalled();
    rerender(<DrawingOverlay {...props} selectedId="fib-1" />);
    fireEvent.pointerDown(canvas, { clientX: 50, clientY: 140, pointerId: 2 });
    fireEvent.pointerMove(canvas, { clientX: 60, clientY: 150, pointerId: 2 });
    fireEvent.pointerUp(canvas, { pointerId: 2 });
    expect(onCommit).toHaveBeenLastCalledWith([
      expect.objectContaining({
        id: "fib-1",
        anchors: [{ logical: 60, price: 150 }, { logical: 20, price: 110 }],
      }),
    ]);
    expect(context.setLineDash).toHaveBeenCalledWith([5, 4]);
    expect(context.moveTo).toHaveBeenCalledWith(0, 150);
    fireEvent.pointerDown(canvas, { clientX: 140, clientY: 75, pointerId: 3 });
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });

  it("selects an existing drawing and deselects it on an outside tap", () => {
    const drawing: DrawingObject = {
      id: "line-1",
      type: "trend",
      anchors: [{ logical: 10, price: 10 }, { logical: 20, price: 20 }],
      style: { color: "#fff", lineWidth: 1 },
      locked: false,
      hidden: false,
    };
    const onSelect = vi.fn();
    const { container } = render(
      <DrawingOverlay
        {...overlayProps({ drawings: [drawing], tool: "select", onSelect })}
      />,
    );
    const canvas = container.querySelector("canvas") as HTMLCanvasElement;
    fireEvent.pointerDown(canvas, { clientX: 15, clientY: 15, pointerId: 1 });
    fireEvent.pointerDown(canvas, { clientX: 100, clientY: 100, pointerId: 2 });
    expect(onSelect).toHaveBeenNthCalledWith(1, "line-1");
    expect(onSelect).toHaveBeenNthCalledWith(2, null);
  });
});
