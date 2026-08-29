export type ChartPriceFormat = {
  type: "custom";
  precision: number;
  minMove: number;
  formatter: (price: number) => string;
};

export function chartPriceFormat(tickSize: number): ChartPriceFormat | null {
  if (!Number.isFinite(tickSize) || tickSize <= 0) return null;
  for (let precision = 0; precision <= 12; precision += 1) {
    const scaled = tickSize * 10 ** precision;
    if (Math.abs(scaled - Math.round(scaled)) < 1e-9) {
      return {
        type: "custom",
        precision,
        minMove: tickSize,
        formatter: (price: number) =>
          price.toFixed(precision).replace(/^(-?)0\./, "$1."),
      };
    }
  }
  return null;
}
