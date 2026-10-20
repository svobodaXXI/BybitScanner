import { describe, expect, it } from "vitest";
import type { TimestampDrawing } from "./geometryReviewDraft";
import { compareRayCorrection } from "./rayCorrectionComparison";

const scanner: TimestampDrawing = {
  id: "upper", type: "ray",
  anchors: [
    { bar_open_time_ms: 1_800_000_000_000, price: 100 },
    { bar_open_time_ms: 1_800_000_300_000, price: 99 },
  ],
};
describe("two-point ray geometry feedback", () => {
  it("keeps both anchor shifts and reports original/corrected slope", () => {
    const corrected: TimestampDrawing = {
      ...scanner,
      anchors: [
        { bar_open_time_ms: 1_800_000_000_000, price: 101 },
        { bar_open_time_ms: 1_800_000_600_000, price: 99 },
      ],
    };
    const delta = compareRayCorrection(scanner, corrected);
    expect(delta.anchorChanges[0].priceShift).toBe(1);
    expect(delta.anchorChanges[1].barShiftMs).toBe(300_000);
    expect(delta.originalSlopePerHour).toBeCloseTo(-12);
    expect(delta.correctedSlopePerHour).toBeCloseTo(-12);
    expect(delta.slopeDeltaPerHour).toBeCloseTo(0);
  });
  it("denies mismatched identities, one-point rays, and coincident or reversed times", () => {
    expect(() => compareRayCorrection(scanner, { ...scanner, id: "lower" })).toThrow();
    expect(() => compareRayCorrection(scanner, { ...scanner, anchors: [scanner.anchors[0]] })).toThrow();
    expect(() => compareRayCorrection(scanner, { ...scanner, anchors: [scanner.anchors[1], scanner.anchors[0]] })).toThrow();
    expect(() => compareRayCorrection(scanner, { ...scanner, anchors: [scanner.anchors[0], scanner.anchors[0]] })).toThrow();
  });
});
