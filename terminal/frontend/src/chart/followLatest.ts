export const FOLLOW_LATEST_THRESHOLD_BARS = 1.5;

export function isAtLatest(
  range: { from: number; to: number } | null,
  candleCount: number,
): boolean {
  return (
    range !== null && range.to >= candleCount - 1 - FOLLOW_LATEST_THRESHOLD_BARS
  );
}
