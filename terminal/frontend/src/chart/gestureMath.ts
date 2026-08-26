export const PINCH_SCALE_DEAD_ZONE = 0.03;
export const PINCH_AXIS_DOMINANCE_RATIO = 1.55;

export type PinchAxes = "NONE" | "X" | "Y" | "XY";

export interface PinchDelta {
  axes: PinchAxes;
  xScale: number;
  yScale: number;
  xLogDelta: number;
  yLogDelta: number;
}

export function calculateDirectionalPinch(
  startDx: number,
  startDy: number,
  currentDx: number,
  currentDy: number,
): PinchDelta {
  const safeRatio = (current: number, start: number) =>
    Math.max(0.05, current) / Math.max(8, start);
  const rawX = Math.log(safeRatio(currentDx, startDx));
  const rawY = Math.log(safeRatio(currentDy, startDy));
  let x = Math.abs(rawX) < PINCH_SCALE_DEAD_ZONE ? 0 : rawX;
  let y = Math.abs(rawY) < PINCH_SCALE_DEAD_ZONE ? 0 : rawY;
  if (Math.abs(x) > Math.abs(y) * PINCH_AXIS_DOMINANCE_RATIO) y = 0;
  else if (Math.abs(y) > Math.abs(x) * PINCH_AXIS_DOMINANCE_RATIO) x = 0;
  return {
    axes: x === 0 && y === 0 ? "NONE" : y === 0 ? "X" : x === 0 ? "Y" : "XY",
    xScale: Math.exp(x),
    yScale: Math.exp(y),
    xLogDelta: x,
    yLogDelta: y,
  };
}

export function scaleRangeAroundAnchor(
  from: number,
  to: number,
  anchor: number,
  scale: number,
) {
  const safeScale = Math.max(0.12, Math.min(8, scale));
  return {
    from: anchor - (anchor - from) / safeScale,
    to: anchor + (to - anchor) / safeScale,
  };
}

export function translatePriceRangeByPixels(
  range: { from: number; to: number },
  deltaY: number,
  plotHeight: number,
) {
  if (!(plotHeight > 0)) return range;
  const priceDelta = deltaY * (range.to - range.from) / plotHeight;
  return {
    from: range.from + priceDelta,
    to: range.to + priceDelta,
  };
}

export function translateLogicalRangeByPixels(
  range: { from: number; to: number },
  deltaX: number,
  plotWidth: number,
) {
  if (!(plotWidth > 0)) return range;
  const logicalDelta = -deltaX * (range.to - range.from) / plotWidth;
  return {
    from: range.from + logicalDelta,
    to: range.to + logicalDelta,
  };
}
