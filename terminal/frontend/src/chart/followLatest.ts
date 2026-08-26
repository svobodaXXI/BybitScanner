export const FOLLOW_LATEST_THRESHOLD_BARS = 1.5;
export const DEFAULT_RIGHT_OFFSET_BARS = 18;

export function isAtLatest(
  range: { from: number; to: number } | null,
  candleCount: number,
): boolean {
  return (
    range !== null && range.to >= candleCount - 1 - FOLLOW_LATEST_THRESHOLD_BARS
  );
}

export function replaceSeriesDataPreservingViewport<T>(
  data: readonly T[],
  followLatest: boolean,
  series: { setData(next: T[]): void },
  timeScale: {
    getVisibleLogicalRange(): { from: number; to: number } | null;
    setVisibleLogicalRange(range: { from: number; to: number }): void;
    scrollToPosition(position: number, animated: boolean): void;
  },
  rightOffset = DEFAULT_RIGHT_OFFSET_BARS,
): void {
  const preservedRange = followLatest
    ? null
    : timeScale.getVisibleLogicalRange();
  series.setData([...data]);
  if (followLatest) {
    timeScale.scrollToPosition(rightOffset, false);
  } else if (preservedRange) {
    timeScale.setVisibleLogicalRange(preservedRange);
  }
}
