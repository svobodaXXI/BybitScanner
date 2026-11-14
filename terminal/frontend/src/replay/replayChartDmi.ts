/** Read-only standard Wilder DMI over the CLOSED M5 chart history.
 * Matches research/wilder_dmi.py seeds: TR RMA from first bar, +/-DM
 * RMA from first 14 changes, ADX RMA from 14 DX observations.
 * No orders, Scanner signals, future candles or trading decisions.
 */
import type { ReplayCandle, ReplayDmiPoint } from "./replayModel";

export function chartWilderDmi(
  candles: readonly ReplayCandle[], length = 14, smoothing = 14,
): ReplayDmiPoint[] {
  const n = length;
  const k = smoothing;
  if (n < 2 || k < 2) throw new Error("Invalid Wilder DMI periods");
  let trCount = 0, trSum = 0, atr: number | null = null;
  let dmCount = 0, plusSum = 0, minusSum = 0;
  let plusRma: number | null = null, minusRma: number | null = null;
  let dxCount = 0, dxSum = 0, adx: number | null = null;
  const out: ReplayDmiPoint[] = [];
  for (let i = 0; i < candles.length; i++) {
    const bar = candles[i];
    const prev = candles[i - 1];
    if (bar.end_ms - bar.start_ms !== 300_000 ||
        (prev && bar.start_ms !== prev.end_ms) ||
        ![bar.open, bar.high, bar.low, bar.close].every(Number.isFinite) ||
        bar.low <= 0 || bar.high < Math.max(bar.open, bar.close) ||
        bar.low > Math.min(bar.open, bar.close)) {
      throw new Error("Closed contiguous M5 required for DMI");
    }
    const tr = prev ? Math.max(bar.high - bar.low,
      Math.abs(bar.high - prev.close), Math.abs(bar.low - prev.close)) :
      bar.high - bar.low;
    const up = prev ? bar.high - prev.high : 0;
    const down = prev ? prev.low - bar.low : 0;
    const plusDm = up > 0 && up > down ? up : 0;
    const minusDm = down > 0 && down > up ? down : 0;
    if (atr === null) {
      trSum += tr;
      if (++trCount === n) atr = trSum / n;
    } else {
      atr = (atr * (n - 1) + tr) / n;
    }
    if (prev) {
      if (plusRma === null) {
        plusSum += plusDm;
        minusSum += minusDm;
        if (++dmCount === n) {
          plusRma = plusSum / n;
          minusRma = minusSum / n;
        }
      } else {
        plusRma = (plusRma * (n - 1) + plusDm) / n;
        minusRma = (minusRma! * (n - 1) + minusDm) / n;
      }
    }
    let plus_di: number | null = null;
    let minus_di: number | null = null;
    if (atr !== null && plusRma !== null && minusRma !== null) {
      plus_di = atr === 0 ? 0 : 100 * plusRma / atr;
      minus_di = atr === 0 ? 0 : 100 * minusRma / atr;
      const both = plus_di + minus_di;
      const dx = both === 0 ? 0 : 100 * Math.abs(plus_di - minus_di) / both;
      if (adx === null) {
        dxSum += dx;
        if (++dxCount === k) adx = dxSum / k;
      } else {
        adx = (adx * (k - 1) + dx) / k;
      }
    }
    out.push({ time_ms: bar.end_ms, plus_di, minus_di, adx });
  }
  return out;
}
