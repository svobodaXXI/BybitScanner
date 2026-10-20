import type { TimestampDrawing } from "./geometryReviewDraft";
import { compareRayCorrection, type RayDelta } from "./rayCorrectionComparison";

export type PatternBoundaries = {
  upper: TimestampDrawing;
  lower: TimestampDrawing;
};

export type PatternGeometryDelta = {
  upper: RayDelta;
  lower: RayDelta;
  sharedStartMs: number;
  sharedEndMs: number;
  originalWidthAtStart: number;
  correctedWidthAtStart: number;
  originalWidthAtEnd: number;
  correctedWidthAtEnd: number;
  widthChangeAtStart: number;
  widthChangeAtEnd: number;
};

/**
 * Strict two-boundary comparison on the shared timestamp interval.
 * Never extrapolates beyond both original and corrected anchor spans.
 */
export function comparePatternBoundaries(
  original: PatternBoundaries,
  corrected: PatternBoundaries,
): PatternGeometryDelta {
  const upper = compareRayCorrection(original.upper, corrected.upper);
  const lower = compareRayCorrection(original.lower, corrected.lower);
  if (original.upper.id === original.lower.id || corrected.upper.id === corrected.lower.id)
    throw new Error("Upper and lower boundaries must have distinct identities");

  const lines = [original.upper, original.lower, corrected.upper, corrected.lower];
  const sharedStartMs = Math.max(...lines.map((line) => line.anchors[0].bar_open_time_ms));
  const sharedEndMs = Math.min(...lines.map((line) => line.anchors[1].bar_open_time_ms));
  if (sharedStartMs >= sharedEndMs)
    throw new Error("No shared timestamp interval between boundary anchors");

  const at = (line: TimestampDrawing, time: number) => {
    const [first, second] = line.anchors;
    return first.price + (second.price - first.price) *
      ((time - first.bar_open_time_ms) / (second.bar_open_time_ms - first.bar_open_time_ms));
  };
  const width = (pair: PatternBoundaries, time: number) =>
    at(pair.upper, time) - at(pair.lower, time);
  const originalWidthAtStart = width(original, sharedStartMs);
  const correctedWidthAtStart = width(corrected, sharedStartMs);
  const originalWidthAtEnd = width(original, sharedEndMs);
  const correctedWidthAtEnd = width(corrected, sharedEndMs);
  if (![originalWidthAtStart, correctedWidthAtStart, originalWidthAtEnd, correctedWidthAtEnd].every(Number.isFinite))
    throw new Error("Invalid pattern width");
  if ([originalWidthAtStart, correctedWidthAtStart, originalWidthAtEnd, correctedWidthAtEnd].some((v) => v <= 0))
    throw new Error("Upper boundary must remain above lower boundary");

  return {
    upper, lower, sharedStartMs, sharedEndMs,
    originalWidthAtStart, correctedWidthAtStart,
    originalWidthAtEnd, correctedWidthAtEnd,
    widthChangeAtStart: correctedWidthAtStart - originalWidthAtStart,
    widthChangeAtEnd: correctedWidthAtEnd - originalWidthAtEnd,
  };
}
