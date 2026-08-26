import { describe, expect, it } from "vitest";
import {
  calculateDirectionalPinch,
  scaleRangeAroundAnchor,
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

  it("ignores jitter and suppresses the dominated axis", () => {
    expect(calculateDirectionalPinch(100, 100, 102, 98).axes).toBe("NONE");
    expect(calculateDirectionalPinch(100, 100, 150, 104).axes).toBe("X");
  });

  it("keeps an anchor at the same normalized position", () => {
    const range = scaleRangeAroundAnchor(0, 100, 25, 2);
    expect(range).toEqual({ from: 12.5, to: 62.5 });
    expect((25 - range.from) / (range.to - range.from)).toBe(0.25);
  });
});
