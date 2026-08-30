export const DRAWING_SCHEMA_VERSION = 1;
export const FIBONACCI_LEVELS = [
  0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618, 2.618, 3.618, 4.236,
] as const;

export type DrawingTool =
  | "select"
  | "crosshair"
  | "trend"
  | "horizontal"
  | "ray"
  | "horizontal-ray"
  | "vertical"
  | "fibonacci"
  | "ruler"
  | "rectangle";
export type DrawingType = Exclude<DrawingTool, "select" | "crosshair">;
export interface DrawingAnchor {
  logical: number;
  price: number;
}
export interface DrawingObject {
  id: string;
  type: DrawingType;
  anchors: DrawingAnchor[];
  style: { color: string; lineWidth: number };
  locked: boolean;
  hidden: boolean;
}
export interface DrawingDocument {
  version: 1;
  drawings: DrawingObject[];
}

export const requiredAnchors = (type: DrawingType) =>
  type === "horizontal" || type === "horizontal-ray" || type === "vertical"
    ? 1
    : 2;
export const createDrawing = (
  type: DrawingType,
  anchor: DrawingAnchor,
): DrawingObject => ({
  id:
    globalThis.crypto?.randomUUID?.() ??
    `drawing-${Date.now()}-${Math.random()}`,
  type,
  anchors: [anchor],
  style: { color: "#e0b45b", lineWidth: 1.5 },
  locked: false,
  hidden: false,
});
export const moveAnchor = (
  drawing: DrawingObject,
  index: number,
  anchor: DrawingAnchor,
) => ({
  ...drawing,
  anchors: drawing.anchors.map((value, cursor) =>
    cursor === index ? anchor : value,
  ),
});
export const moveDrawing = (
  drawing: DrawingObject,
  logicalDelta: number,
  priceDelta: number,
) => ({
  ...drawing,
  anchors: drawing.anchors.map((anchor) => ({
    logical: anchor.logical + logicalDelta,
    price: anchor.price + priceDelta,
  })),
});
export const serializeDrawings = (drawings: DrawingObject[]) =>
  JSON.stringify({ version: DRAWING_SCHEMA_VERSION, drawings });
export function deserializeDrawings(value: string | null): DrawingObject[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value) as DrawingDocument;
    return parsed.version === DRAWING_SCHEMA_VERSION &&
      Array.isArray(parsed.drawings)
      ? parsed.drawings
      : [];
  } catch {
    return [];
  }
}
export function fibonacciPrices(first: number, second: number) {
  return FIBONACCI_LEVELS.map((level) => ({
    level,
    price: first + (second - first) * level,
  }));
}
export function fibonacciBands(first: number, second: number) {
  const levels = fibonacciPrices(first, second);
  return levels.slice(0, -1).map((from, index) => ({
    from,
    to: levels[index + 1],
  }));
}
export const fibonacciLabel = (
  level: number,
  price: number,
  formatPrice: (value: number) => string,
) => `${level}  ${formatPrice(price)}`;
export function rulerMeasurement(
  origin: DrawingAnchor,
  destination: DrawingAnchor,
  candleSeconds = 300,
) {
  const priceDelta = destination.price - origin.price;
  const bars = Math.round(Math.abs(destination.logical - origin.logical));
  return {
    priceDelta,
    percentDelta: origin.price === 0 ? 0 : (priceDelta / origin.price) * 100,
    bars,
    elapsedSeconds: bars * candleSeconds,
  };
}

export class DrawingHistory {
  private past: DrawingObject[][] = [];
  private future: DrawingObject[][] = [];
  constructor(public current: DrawingObject[] = []) {}
  commit(next: DrawingObject[]) {
    this.past.push(this.current);
    this.current = next;
    this.future = [];
    return this.current;
  }
  undo() {
    const value = this.past.pop();
    if (!value) return this.current;
    this.future.push(this.current);
    this.current = value;
    return this.current;
  }
  redo() {
    const value = this.future.pop();
    if (!value) return this.current;
    this.past.push(this.current);
    this.current = value;
    return this.current;
  }
}

export function clearDrawingHistory(history: DrawingHistory): DrawingObject[] {
  return history.commit([]);
}
