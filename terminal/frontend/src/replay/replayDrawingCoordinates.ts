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
