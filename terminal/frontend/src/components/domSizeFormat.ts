const trimFraction = (value: number, fractionDigits: number) =>
  value
    .toFixed(fractionDigits)
    .replace(/\.0+$/, "")
    .replace(/(\.\d*?)0+$/, "$1");

export function formatDomSize(value: number): string {
  if (value >= 1_000_000) return `${trimFraction(value / 1_000_000, 2)}M`;
  if (value >= 1_000) return `${trimFraction(value / 1_000, 2)}K`;
  return trimFraction(value, 3);
}
