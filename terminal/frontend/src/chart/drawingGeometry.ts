import type { DrawingAnchor, DrawingObject } from "./drawingModel";

export interface Point {
  x: number;
  y: number;
}
export const pointDistance = (a: Point, b: Point) =>
  Math.hypot(a.x - b.x, a.y - b.y);
export function segmentDistance(point: Point, a: Point, b: Point) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  if (dx === 0 && dy === 0) return pointDistance(point, a);
  const t = Math.max(
    0,
    Math.min(
      1,
      ((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy),
    ),
  );
  return pointDistance(point, { x: a.x + t * dx, y: a.y + t * dy });
}
export function nearestOhlcAnchor(
  anchor: DrawingAnchor,
  candles: readonly {
    open: number;
    high: number;
    low: number;
    close: number;
  }[],
  logicalToX: (logical: number) => number | null,
  priceToY: (price: number) => number | null,
  radius = 14,
) {
  const index = Math.max(
    0,
    Math.min(candles.length - 1, Math.round(anchor.logical)),
  );
  let best = anchor;
  let distance = radius;
  for (
    let cursor = Math.max(0, index - 1);
    cursor <= Math.min(candles.length - 1, index + 1);
    cursor++
  ) {
    for (const price of [
      candles[cursor].open,
      candles[cursor].high,
      candles[cursor].low,
      candles[cursor].close,
    ]) {
      const x = logicalToX(cursor);
      const y = priceToY(price);
      const ax = logicalToX(anchor.logical);
      const ay = priceToY(anchor.price);
      if (x === null || y === null || ax === null || ay === null) continue;
      const candidate = Math.hypot(x - ax, y - ay);
      if (candidate < distance) {
        distance = candidate;
        best = { logical: cursor, price };
      }
    }
  }
  return best;
}
export function drawingLabel(drawing: DrawingObject) {
  return `${drawing.type} drawing`;
}
