import { describe, expect, it } from "vitest";
import {
  calculateDirectionalPinch,
  beginDirectionalPinch,
  advanceDirectionalPinch,
  scaleRangeAroundAnchor,
  translateLogicalRangeByPixels,
  translatePriceRangeByPixels,
} from "./gestureMath";

describe("directional pinch math", () => {
  it.each([
    [100, 100, 140, 101, "X", 1],
    [100, 100, 70, 99, "X", -1],
    [100, 100, 101, 140, "Y", 1],
    [100, 100, 99, 70, "Y", -1],
    [100, 100, 140, 140, "XY", 1],
  ] as const)(
    "classifies directional motion",
    (dx0, dy0, dx, dy, axes, sign) => {
      const result = calculateDirectionalPinch(dx0, dy0, dx, dy);
      expect(result.axes).toBe(axes);
      const delta = axes === "Y" ? result.yLogDelta : result.xLogDelta;
      expect(Math.sign(delta)).toBe(sign);
    },
  );

  it("keeps independent signs for a mixed diagonal gesture", () => {
    const result = calculateDirectionalPinch(100, 100, 135, 75);
    expect(result.axes).toBe("XY");
    expect(result.xLogDelta).toBeGreaterThan(0);
    expect(result.yLogDelta).toBeLessThan(0);
  });

  it("ignores small independent axis jitter", () => {
    expect(calculateDirectionalPinch(100, 100, 102, 98).axes).toBe("NONE");
    expect(calculateDirectionalPinch(100, 100, 150, 104).axes).toBe("X");
  });

  it.each([1, -1])("does not reverse when fingers cross (orientation %s)", (sign) => {
    let state = beginDirectionalPinch(0, sign * 100);
    let previous = 1;
    for (const separation of [90, 40, 8, 0, -8, -100, -300, -500]) {
      const result = advanceDirectionalPinch(state, 0, sign * separation);
      expect(result.yScale).toBeLessThanOrEqual(previous);
      expect(result.xScale).toBe(1);
      expect(result.yScale).toBeGreaterThanOrEqual(0.12 - 1e-12);
      previous = result.yScale;
      state = result.state;
    }
    expect(previous).toBeCloseTo(0.12);
    const reversed = advanceDirectionalPinch(state, 0, sign * -490);
    expect(reversed.yScale).toBeGreaterThan(previous);
  });

  it("has no initial jump with aligned fingers and locks the first deliberate direction", () => {
    let state = beginDirectionalPinch(0, 2);
    const rest = advanceDirectionalPinch(state, 0, 2);
    expect(rest.axes).toBe("NONE");
    expect(rest.yScale).toBe(1);
    const spread = advanceDirectionalPinch(rest.state, 0, -18);
    expect(spread.yScale).toBeGreaterThan(1);
    const reverse = advanceDirectionalPinch(spread.state, 0, 12);
    expect(reverse.yScale).toBeLessThan(1);
  });

  it("keeps the accumulated scale of one axis when the other becomes dominant", () => {
    const first = advanceDirectionalPinch(beginDirectionalPinch(100, 100), 140, 100);
    const second = advanceDirectionalPinch(first.state, 140, 250);
    expect(second.axes).toBe("Y");
    expect(second.xScale).toBe(first.xScale);
    expect(second.yScale).toBeGreaterThan(first.yScale);
    const back = advanceDirectionalPinch(second.state, 140, 100);
    expect(back.yScale).toBeCloseTo(1);
    expect(back.xScale).toBe(first.xScale);
  });

  it("returns the changed axis to its initial scale instead of leaving a stale viewport", () => {
    const moved = advanceDirectionalPinch(beginDirectionalPinch(100, 100), 120, 100);
    const back = advanceDirectionalPinch(moved.state, 100, 100);
    expect(back.axes).toBe("X");
    expect(back.xScale).toBeCloseTo(1);
  });

  it("keeps an anchor at the same normalized position", () => {
    const range = scaleRangeAroundAnchor(0, 100, 25, 2);
    expect(range).toEqual({ from: 12.5, to: 62.5 });
    expect((25 - range.from) / (range.to - range.from)).toBe(0.25);
  });

  it("translates the price viewport without changing its span", () => {
    const moved = translatePriceRangeByPixels(
      { from: 90, to: 110 },
      50,
      200,
    );
    expect(moved).toEqual({ from: 95, to: 115 });
    expect(moved.to - moved.from).toBe(20);
  });

  it("translates logical range from the fixed drag origin without viewport feedback", () => {
    const origin = { from: 100, to: 200 };
    expect(translateLogicalRangeByPixels(origin, 20, 400)).toEqual({
      from: 95,
      to: 195,
    });
    expect(translateLogicalRangeByPixels(origin, 40, 400)).toEqual({
      from: 90,
      to: 190,
    });
  });
});
