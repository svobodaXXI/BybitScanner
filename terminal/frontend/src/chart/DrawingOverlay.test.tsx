import { fireEvent, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DrawingObject } from "./drawingModel";
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
