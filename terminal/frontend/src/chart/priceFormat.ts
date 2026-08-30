export type ChartPriceFormat = {
  type: "custom";
  precision: number;
  minMove: number;
  formatter: (price: number) => string;
};

const compactSmallPrice = (price: number, precision: number) => {
  const formatted = price.toFixed(precision);
  const match = formatted.match(/^(-?)0\.(0{2,})([1-9]\d*)$/);
  return match ? `${match[1]}(${match[2].length})${match[3]}` : formatted;
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
        formatter: (price: number) => compactSmallPrice(price, precision),
      };
    }
  }
  return null;
}
