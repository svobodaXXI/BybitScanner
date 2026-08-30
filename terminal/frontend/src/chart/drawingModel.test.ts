import { describe, expect, it } from "vitest";
import {
  createDrawing,
  clearDrawingHistory,
  DrawingHistory,
  deserializeDrawings,
  FIBONACCI_LEVELS,
  fibonacciBands,
  fibonacciLabel,
  fibonacciPrices,
  moveAnchor,
  moveDrawing,
  rulerMeasurement,
  serializeDrawings,
} from "./drawingModel";

describe("drawing model", () => {
  it("creates and moves anchors and objects", () => {
    const drawing = createDrawing("trend", { logical: 1, price: 10 });
    const withSecond = {
      ...drawing,
      anchors: [...drawing.anchors, { logical: 2, price: 12 }],
    };
    expect(
      moveAnchor(withSecond, 1, { logical: 3, price: 13 }).anchors[1].price,
    ).toBe(13);
    expect(moveDrawing(withSecond, 2, -1).anchors[0]).toEqual({
      logical: 3,
      price: 9,
    });
  });
  it("keeps ray type while either anchor is edited", () => {
    const ray = createDrawing("ray", { logical: 1, price: 10 });
    const complete = {
      ...ray,
      anchors: [...ray.anchors, { logical: 2, price: 12 }],
    };
    expect(moveAnchor(complete, 0, { logical: 0, price: 9 }).type).toBe("ray");
    expect(moveAnchor(complete, 1, { logical: 3, price: 13 }).type).toBe("ray");
  });
  it("supports delete through history plus undo and redo", () => {
    const drawing = createDrawing("horizontal", { logical: 1, price: 10 });
    const history = new DrawingHistory([drawing]);
    history.commit([]);
    expect(history.current).toHaveLength(0);
    history.undo();
    expect(history.current).toHaveLength(1);
    history.redo();
    expect(history.current).toHaveLength(0);
  });
  it("clears only drawing history and serializes an empty drawing document", () => {
    const orders = [{ id: "limit-1" }];
    const history = new DrawingHistory([
      createDrawing("horizontal", { logical: 1, price: 10 }),
    ]);
    const cleared = clearDrawingHistory(history);
    expect(cleared).toEqual([]);
    expect(serializeDrawings(cleared)).toBe('{"version":1,"drawings":[]}');
    expect(orders).toEqual([{ id: "limit-1" }]);
  });
  it("round trips only the supported persistence version", () => {
    const drawings = [createDrawing("vertical", { logical: 4, price: 10 })];
    expect(deserializeDrawings(serializeDrawings(drawings))).toEqual(drawings);
    expect(deserializeDrawings('{"version":2,"drawings":[]}')).toEqual([]);
  });
  it("calculates fib in both directions and ruler values", () => {
    expect(fibonacciPrices(100, 200).map((x) => x.price)).toContain(150);
    expect(fibonacciPrices(200, 100).map((x) => x.price)).toContain(150);
    const measurement = rulerMeasurement(
      { logical: 1, price: 100 },
      { logical: 18, price: 102.37 },
    );
    expect(measurement.bars).toBe(17);
    expect(measurement.priceDelta).toBeCloseTo(2.37);
    expect(measurement.percentDelta).toBeCloseTo(2.37);
  });

  it("keeps Ruler price and percentage signs directed from origin to destination", () => {
    const upward = rulerMeasurement(
      { logical: 10, price: 100 },
      { logical: 20, price: 125 },
    );
    expect(upward.priceDelta).toBe(25);
    expect(upward.percentDelta).toBe(25);

    const downward = rulerMeasurement(
      { logical: 10, price: 125 },
      { logical: 20, price: 100 },
    );
    expect(downward.priceDelta).toBe(-25);
    expect(downward.percentDelta).toBe(-20);
  });

  it("uses the binding retracement and extension levels", () => {
    expect(FIBONACCI_LEVELS).toEqual([
      0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618, 2.618, 3.618, 4.236,
    ]);
  });

  it("calculates genuine extensions in both anchor directions", () => {
    const forward = fibonacciPrices(100, 110);
    const reverse = fibonacciPrices(110, 100);
    expect(forward.find((item) => item.level === 1.618)?.price).toBeCloseTo(116.18);
    expect(reverse.find((item) => item.level === 1.618)?.price).toBeCloseTo(93.82);
  });

  it("produces adjacent fill bands and coefficient-price labels", () => {
    const bands = fibonacciBands(0.07, 0.080841);
    expect(bands).toHaveLength(FIBONACCI_LEVELS.length - 1);
    expect(bands[0].from.level).toBe(0);
    expect(bands[0].to.level).toBe(0.236);
    const level = fibonacciPrices(0.07, 0.080841).find((item) => item.level === 0.618)!;
    expect(fibonacciLabel(level.level, level.price, (price) => price.toFixed(4)))
      .toBe("0.618  0.0767");
  });
});
