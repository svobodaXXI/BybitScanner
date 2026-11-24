const PINCH_DEAD_ZONE_PX = 4;
const PINCH_ORIENTATION_MIN_PX = 8;
const MIN_SCALE = 0.12;
const MAX_SCALE = 8;

export type PinchAxes = "NONE" | "X" | "Y" | "XY";

interface PinchAxisState {
  start: number;
  orientation: number;
  previous: number;
  logScale: number;
}
export interface DirectionalPinchState {
  x: PinchAxisState;
  y: PinchAxisState;
}

const startAxis = (start: number): PinchAxisState => ({
  start,
  orientation: Math.abs(start) >= PINCH_ORIENTATION_MIN_PX ? Math.sign(start) : 0,
  previous: 0,
  logScale: 0,
});

export function beginDirectionalPinch(dx: number, dy: number): DirectionalPinchState {
  return { x: startAxis(dx), y: startAxis(dy) };
}

function advanceAxis(axis: PinchAxisState, current: number, pixelsPerLog: number): PinchAxisState {
  const displacement = current - axis.start;
  // Keep the original finger ordering even after crossing. An initially
  // aligned axis acquires its orientation only on the first deliberate move.
  const orientation = axis.orientation ||
    (Math.abs(displacement) > PINCH_DEAD_ZONE_PX ? Math.sign(displacement) : 0);
  const directed = displacement * orientation;
  const previous = Math.sign(directed) * Math.max(0, Math.abs(directed) - PINCH_DEAD_ZONE_PX) / pixelsPerLog;
  // Incremental saturation avoids a long dead travel when reversing at a limit.
  const logScale = Math.max(Math.log(MIN_SCALE), Math.min(Math.log(MAX_SCALE),
    axis.logScale + previous - axis.previous));
  return { ...axis, orientation, previous, logScale };
}

export function advanceDirectionalPinch(state: DirectionalPinchState, dx: number, dy: number) {
  const x = advanceAxis(state.x, dx, 160);
  const y = advanceAxis(state.y, dy, 140);
  const xChanged = x.logScale !== state.x.logScale;
  const yChanged = y.logScale !== state.y.logScale;
  const axes: PinchAxes = xChanged ? (yChanged ? "XY" : "X") : yChanged ? "Y" : "NONE";
  return {
    state: { x, y },
    axes,
    xScale: Math.exp(x.logScale),
    yScale: Math.exp(y.logScale),
    xLogDelta: x.logScale,
    yLogDelta: y.logScale,
  };
}

// Single-step projection for deterministic callers and tests.
export function calculateDirectionalPinch(startDx: number, startDy: number, currentDx: number, currentDy: number) {
  return advanceDirectionalPinch(beginDirectionalPinch(startDx, startDy), currentDx, currentDy);
}

export function scaleRangeAroundAnchor(
  from: number,
  to: number,
  anchor: number,
  scale: number,
) {
  const safeScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));
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
