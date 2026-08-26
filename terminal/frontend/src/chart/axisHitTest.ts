export type ChartAxisTarget = "TIME" | "PRICE" | "PLOT";

export function chartAxisTarget(
  point: { x: number; y: number },
  width: number,
  height: number,
  priceScaleWidth: number,
  timeScaleHeight: number,
): ChartAxisTarget {
  if (point.y > height - timeScaleHeight) return "TIME";
  if (point.x > width - priceScaleWidth) return "PRICE";
  return "PLOT";
}
