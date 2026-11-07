import type { TimestampDrawing } from "./geometryReviewDraft";

/** Compare a scanner ray with a manually corrected ray, retaining both endpoints. */
export type RayDelta = {
  boundaryId: string;
  anchorChanges: { barShiftMs: number; priceShift: number; priceShiftPercent: number }[];
  originalSlopePerHour: number;
  correctedSlopePerHour: number;
  slopeDeltaPerHour: number;
};

function rayEndpoints(drawing: TimestampDrawing) {
  if (!["ray", "trend"].includes(drawing.type) || drawing.anchors.length !== 2)
    throw new Error("A two-anchor ray or trend is required");
  const [a, b] = drawing.anchors;
  if (!a || !b || ![a.bar_open_time_ms, b.bar_open_time_ms, a.price, b.price].every(Number.isFinite)
    || !Number.isSafeInteger(a.bar_open_time_ms) || !Number.isSafeInteger(b.bar_open_time_ms)
    || a.bar_open_time_ms < 0 || b.bar_open_time_ms <= a.bar_open_time_ms || a.price <= 0 || b.price <= 0)
    throw new Error("Invalid ray anchors or timestamp order");
  return [a, b] as const;
}

export function compareRayCorrection(original: TimestampDrawing, corrected: TimestampDrawing): RayDelta {
  if (!original.id || original.id !== corrected.id || original.type !== corrected.type)
    throw new Error("Different boundary identities");
  // MIRROR horizontal source levels have one real anchor, not a fitted
  // second point. Compare that anchor directly instead of inventing a ray.
  if (["horizontal", "horizontal-ray"].includes(original.type)) {
    if (original.anchors.length !== 1 || corrected.anchors.length !== 1)
      throw new Error("A single frozen horizontal anchor is required");
    const [before] = original.anchors;
    const [after] = corrected.anchors;
    if (![before, after].every((anchor) =>
      Number.isSafeInteger(anchor.bar_open_time_ms) && anchor.bar_open_time_ms >= 0 &&
      Number.isFinite(anchor.price) && anchor.price > 0))
      throw new Error("Invalid horizontal source anchor");
    return {
      boundaryId: original.id,
      anchorChanges: [{
        barShiftMs: after.bar_open_time_ms - before.bar_open_time_ms,
        priceShift: after.price - before.price,
        priceShiftPercent: ((after.price - before.price) / before.price) * 100,
      }],
      originalSlopePerHour: 0,
      correctedSlopePerHour: 0,
      slopeDeltaPerHour: 0,
    };
  }
  const [a, b] = rayEndpoints(original);
  const [c, d] = rayEndpoints(corrected);
  const slope = (first: typeof a, second: typeof b) =>
    (second.price - first.price) / ((second.bar_open_time_ms - first.bar_open_time_ms) / 3_600_000);
  const originalSlopePerHour = slope(a, b);
  const correctedSlopePerHour = slope(c, d);
  return {
    boundaryId: original.id,
    anchorChanges: [[a, c], [b, d]].map(([before, after]) => ({
      barShiftMs: after.bar_open_time_ms - before.bar_open_time_ms,
      priceShift: after.price - before.price,
      priceShiftPercent: ((after.price - before.price) / before.price) * 100,
    })),
    originalSlopePerHour,
    correctedSlopePerHour,
    slopeDeltaPerHour: correctedSlopePerHour - originalSlopePerHour,
  };
}
