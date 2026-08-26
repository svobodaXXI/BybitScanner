export type ChartPriceFormat = {
  type: "price";
  precision: number;
  minMove: number;
};

export function chartPriceFormat(tickSize: number): ChartPriceFormat | null {
  if (!Number.isFinite(tickSize) || tickSize <= 0) return null;
  for (let precision = 0; precision <= 12; precision += 1) {
    const scaled = tickSize * 10 ** precision;
    if (Math.abs(scaled - Math.round(scaled)) < 1e-9) {
      return { type: "price", precision, minMove: tickSize };
    }
  }
  return null;
}
