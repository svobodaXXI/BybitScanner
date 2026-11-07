/** Manual replay annotations use absolute M5 UTC slots, not the active chart index.
 * Changing between M5 and H1 therefore never moves an annotation in time.
 * This mapping reads only candles already visible at the current replay cursor.
 */
import type { ReplayCandle } from "./replayModel";

export const REPLAY_DRAWING_SLOT_MS = 300_000;
export const timeToDrawingLogical = (timeMs: number) => timeMs / REPLAY_DRAWING_SLOT_MS;
export const drawingLogicalToTime = (logical: number) => logical * REPLAY_DRAWING_SLOT_MS;

export function chartLogicalAtTime(timeMs: number, candles: readonly ReplayCandle[]): number | null {
  if (!candles.length) return null;
  const step = candles[0].end_ms - candles[0].start_ms;
  if (timeMs <= candles[0].start_ms) return (timeMs - candles[0].start_ms) / step;
  const last = candles.length - 1;
  if (timeMs >= candles[last].start_ms)
    return last + (timeMs - candles[last].start_ms) / step;
  for (let i = 1; i < candles.length; i++) {
    if (timeMs <= candles[i].start_ms)
      return i - 1 + (timeMs - candles[i - 1].start_ms) /
        (candles[i].start_ms - candles[i - 1].start_ms);
  }
  return null;
}

export function timeAtChartLogical(logical: number, candles: readonly ReplayCandle[]): number | null {
  if (!candles.length || !Number.isFinite(logical)) return null;
  const step = candles[0].end_ms - candles[0].start_ms;
  const last = candles.length - 1;
  if (logical <= 0) return candles[0].start_ms + logical * step;
  if (logical >= last) return candles[last].start_ms + (logical - last) * step;
  const i = Math.floor(logical);
  return candles[i].start_ms + (logical - i) *
    (candles[i + 1].start_ms - candles[i].start_ms);
}

/**
 * Immutable source geometry is timestamp-based, even when its M5 anchors and
 * retirement both fall within a single displayed H1 candle. Round-to-H1-bar
 * rendering silently drops those short historical lines.
 *
 * This projection uses only the displayed time axis and the already-known
 * retirement; the source line, prices and historical publication are unchanged.
 */
/**
 * An M5 correction remains on the H1 historical chart, but it must not
 * acquire a multi-day H1 ray solely from the chart's coarse time scale.
 * Show its actual two-pivot slope through the time it became publishable.
 * The full open-ended research reference still renders on the M5 chart.
 */
export function automaticGeometryTimeframeCap(
  line: { kind: "MAIN_1H" | "TARGET_1H" | "REFERENCE_5M" | "ACCELERATION_5M";
    available_at_ms: number },
  timeframe: "5m" | "1h",
): number {
  return timeframe === "1h" &&
    (line.kind === "REFERENCE_5M" || line.kind === "ACCELERATION_5M")
    ? line.available_at_ms : Infinity;
}

export function geometryLogicalSegment(
  line: { from_ms: number; retired_at_ms?: number; superseded_at_ms?: number },
  displayedCandles: readonly ReplayCandle[],
): { from: number; to: number } | null {
  const last = displayedCandles.at(-1);
  if (!last) return null;
  // Preserve old anchors and history, but stop the drawn extent when the
  // replacement becomes known. Historical rays must not cross the entire
  // later chart while masquerading as the active trend.
  const untilMs = Math.min(line.retired_at_ms ?? Infinity,
    line.superseded_at_ms ?? Infinity, last.end_ms);
  if (untilMs <= line.from_ms) return null;
  const from = chartLogicalAtTime(line.from_ms, displayedCandles);
  const to = chartLogicalAtTime(untilMs, displayedCandles);
  return from === null || to === null || to <= from ? null : { from, to };
}

/**
 * Project a timestamp onto the NATIVE candlestick coordinates. The chart
 * may carry multiple series/panes whose logical indices need not match a
 * caller-maintained H1 candle array. Use the chart's own H1 bar coordinates
 * and interpolate between their actual UTC times, preserving M5 precision.
 * Never round a five-minute anchor to an hourly open.
 */
export function chartXAtCandleTime(
  atMs: number,
  candles: readonly ReplayCandle[],
  chartTimeToX: (candleStartMs: number) => number | null,
): number | null {
  if (!Number.isFinite(atMs) || candles.length < 2) return null;
  let i = 0;
  while (i + 2 < candles.length && candles[i + 1].start_ms <= atMs) i++;
  // Before/after the loaded window: extrapolate only the axis spacing,
  // not candle prices or a strategy decision. At least two REAL bars exist.
  const a = candles[i], b = candles[i + 1];
  if (b.start_ms <= a.start_ms) return null;
  const ax = chartTimeToX(a.start_ms), bx = chartTimeToX(b.start_ms);
  if (ax === null || bx === null || !Number.isFinite(ax) || !Number.isFinite(bx))
    return null;
  return ax + (bx - ax) * (atMs - a.start_ms) / (b.start_ms - a.start_ms);
}

/**
 * Keep the first H1 movement wick fixed, but pivot the VISIBLE main support/
 * resistance ray onto the most protruding already-closed H1 wick. The four
 * structural pivots and canonical publication remain unchanged. A later
 * candle can tighten the display only when its H1 close is in the replay.
 *
 * BULL main is below all lows (minimum slope); BEAR main above all highs
 * (maximum slope). No future H1 candle can influence a prior frame.
 */
export function wickTightH1MainProjection(
  line: { kind: string; side: "BULL" | "BEAR";
    from_ms: number; to_ms: number; from_price: number; to_price: number },
  closedHours: readonly ReplayCandle[],
  knownAtMs: number,
): { from_ms: number; to_ms: number; from_price: number; to_price: number;
     adjusted: boolean } {
  const original = {
    from_ms: line.from_ms, to_ms: line.to_ms,
    from_price: line.from_price, to_price: line.to_price, adjusted: false,
  };
  if (line.kind !== "MAIN_1H" || !Number.isFinite(knownAtMs) ||
      line.to_ms <= line.from_ms) return original;
  let slope = (line.to_price - line.from_price) / (line.to_ms - line.from_ms);
  let supporting: ReplayCandle | undefined;
  for (const bar of closedHours) {
    if (bar.start_ms <= line.from_ms || bar.end_ms > knownAtMs) continue;
    const wick = line.side === "BULL" ? bar.low : bar.high;
    const candidateSlope = (wick - line.from_price) / (bar.start_ms - line.from_ms);
    if ((line.side === "BULL" && candidateSlope < slope - 1e-18) ||
        (line.side === "BEAR" && candidateSlope > slope + 1e-18)) {
      slope = candidateSlope;
      supporting = bar;
    }
  }
  // The original first anchor is immutable. A real closed candle, not an
  // invented pivot or a backdated future candle, supplies the new second tip.
  return supporting
    ? { from_ms: line.from_ms, to_ms: supporting.start_ms,
        from_price: line.from_price,
        to_price: line.side === "BULL" ? supporting.low : supporting.high,
        adjusted: true }
    : original;
}

export function shortActiveM5Ray(
  from: { x: number; y: number }, through: { x: number; y: number },
  lastCandleX: number, paneWidth: number,
): { x: number; y: number } {
  const dx = through.x - from.x;
  if (!Number.isFinite(dx) || dx <= 0) return through;
  const endX = Math.min(paneWidth, Math.max(through.x, lastCandleX + 36));
  return { x: endX, y: through.y + (through.y - from.y) *
    (endX - through.x) / dx };
}

/**
 * Hide tiny remnants of already-ended lines at the left viewport edge.
 * This affects canvas visibility only: source anchors and archived versions
 * remain untouched and reappear when the user scrolls back to their time.
 */
export function isLeftEdgeHistoricalFragment(
  fromX: number, toX: number, paneWidth: number,
): boolean {
  if (![fromX, toX, paneWidth].every(Number.isFinite) || paneWidth <= 0) return false;
  return fromX < 0 && toX > 0 &&
    toX < Math.min(120, paneWidth * 0.15);
}

/** Replay magnet: only already-visible candle HIGH/LOW, in the selected TF.
 * This adapter maps absolute UTC slots to canvas pixels without rounding
 * 5m anchors to H1 or touching the automatic research geometry.
 */
export function nearestReplayHighLowAnchor(
  anchor: { logical: number; price: number },
  displayedCandles: readonly ReplayCandle[],
  logicalToX: (logical: number) => number | null,
  priceToY: (price: number) => number | null,
  radius = 14,
): { logical: number; price: number } {
  if (!displayedCandles.length) return anchor;
  const rawX = logicalToX(anchor.logical);
  const rawY = priceToY(anchor.price);
  if (rawX === null || rawY === null) return anchor;
  const atMs = drawingLogicalToTime(anchor.logical);
  const pivot = chartLogicalAtTime(atMs, displayedCandles);
  if (pivot === null) return anchor;
  const nearest = Math.max(0, Math.min(displayedCandles.length - 1, Math.round(pivot)));
  let best = anchor, bestDistance = radius;
  for (let i = Math.max(0, nearest - 1);
    i <= Math.min(displayedCandles.length - 1, nearest + 1); i++) {
    const candle = displayedCandles[i];
    const logical = timeToDrawingLogical(candle.start_ms);
    const x = logicalToX(logical);
    if (x === null) continue;
    for (const price of [candle.high, candle.low]) {
      const y = priceToY(price);
      if (y === null) continue;
      const distance = Math.hypot(x - rawX, y - rawY);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = { logical, price };
      }
    }
  }
  return best;
}
