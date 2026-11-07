import { describe, expect, it } from "vitest";
import type { TimestampDrawing } from "./geometryReviewDraft";
import { comparePatternBoundaries } from "./patternBoundaryComparison";

const t0 = 1_800_000_000_000;
const t1 = t0 + 3_600_000;
function ray(id: string, p0: number, p1: number): TimestampDrawing {
  return {
    id, type: "ray",
    anchors: [
      { bar_open_time_ms: t0, price: p0 },
      { bar_open_time_ms: t1, price: p1 },
    ],
  };
}
const original = { upper: ray("upper", 110, 106), lower: ray("lower", 90, 94) };

describe("Pattern boundary corrections", () => {
  it("compares both anchored rays and shape width at the same times", () => {
    const diff = comparePatternBoundaries(original, {
      upper: ray("upper", 111, 105),
      lower: ray("lower", 89, 95),
    });
    expect(diff.originalWidthAtStart).toBe(20);
    expect(diff.correctedWidthAtStart).toBe(22);
    expect(diff.originalWidthAtEnd).toBe(12);
    expect(diff.correctedWidthAtEnd).toBe(10);
    expect(diff.widthChangeAtStart).toBe(2);
    expect(diff.widthChangeAtEnd).toBe(-2);
    expect(diff.upper.anchorChanges).toHaveLength(2);
    expect(diff.lower.anchorChanges).toHaveLength(2);
  });
  it("rejects swapped boundary identity and geometry crossing", () => {
    expect(() => comparePatternBoundaries(original, {
      upper: original.lower, lower: original.upper,
    })).toThrow();
    expect(() => comparePatternBoundaries(original, {
      upper: ray("upper", 90, 90), lower: ray("lower", 100, 100),
    })).toThrow();
  });
  it("requires a shared observation interval", () => {
    const later = (id: string, price: number): TimestampDrawing => ({
      id, type: "ray",
      anchors: [
        { bar_open_time_ms: t1 + 1, price },
        { bar_open_time_ms: t1 + 3_600_000, price },
      ],
    });
    expect(() => comparePatternBoundaries(original, {
      upper: later("upper", 110), lower: later("lower", 90),
    })).toThrow();
  });
});
