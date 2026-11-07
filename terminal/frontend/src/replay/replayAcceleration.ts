/**
 * H-017 visual-only "последнее пятиминутное ускорение".
 * A separate AGAINST-H1-trend research observation, never the blue M5
 * continuation reference and never an order/entry signal.
 *
 * Owner-defined "near" has NO numeric tolerance. Until that is calibrated,
 * publish only the unambiguous subset: M5 pivot 4 actually touches/crosses
 * the already published H1 target at pivot time. All four M5 pivots must be
 * confirmed on closed M5 candles. The source anchors 1 and 3 are immutable
 * meaningful pivots; reject piercing wicks instead of refitting to arbitrary
 * in-between candles.
 */
import {
  appendEarlyPivot, type EarlyPivot,
  type ReplayCandle, type ReplayDocument, type ReplayGeometry,
} from "./replayModel";

export type ReplayAcceleration = Omit<ReplayGeometry, "kind"> & {
  kind: "ACCELERATION_5M";
  pivots: readonly [EarlyPivot, EarlyPivot, EarlyPivot, EarlyPivot];
  target_price_at_fourth: number;
  distance_to_target: number;
  retired_at_ms?: number;
  superseded_at_ms?: number;
};

function isAlignedFour(
  points: readonly EarlyPivot[], side: "BULL" | "BEAR",
): points is [EarlyPivot, EarlyPivot, EarlyPivot, EarlyPivot] {
  if (points.length !== 4) return false;
  const [a,b,c,d] = points;
  return side === "BULL"
    ? a.kind === "LOW" && b.kind === "HIGH" &&
      c.kind === "LOW" && d.kind === "HIGH" &&
      c.price > a.price && d.price > b.price
    : a.kind === "HIGH" && b.kind === "LOW" &&
      c.kind === "HIGH" && d.kind === "LOW" &&
      c.price < a.price && d.price < b.price;
}

function projectedPrice(line: Pick<ReplayGeometry, "from_ms"|"to_ms"|"from_price"|"to_price">, at: number): number {
  return line.from_price + (line.to_price - line.from_price) *
    (at - line.from_ms) / (line.to_ms - line.from_ms);
}

function fourPivotAcceleration(
  bars: readonly ReplayCandle[], four: readonly [EarlyPivot,EarlyPivot,EarlyPivot,EarlyPivot],
  side: "BULL"|"BEAR", main: ReplayGeometry, target: ReplayGeometry,
): ReplayAcceleration | null {
  const [a,,c,d] = four;
  if (a.index >= c.index || c.at_ms <= a.at_ms ||
      d.confirmed_at_ms < c.confirmed_at_ms) return null;
  const slope = (c.price - a.price) / (c.at_ms - a.at_ms);
  if (side === "BULL" ? slope <= 0 : slope >= 0) return null;
  for (let i = a.index + 1; i <= c.index; i++) {
    const candle = bars[i];
    const at = a.price + slope * (candle.start_ms - a.at_ms);
    if (side === "BULL" ? candle.low < at - 1e-9 : candle.high > at + 1e-9)
      return null;
  }
  const targetPrice = projectedPrice(target, d.at_ms);
  const distance = side === "BULL" ? targetPrice - d.price : d.price - targetPrice;
  // No invented ATR / percentage proximity tolerance: proven wick contact only.
  if (distance > 1e-9) return null;
  return {
    kind: "ACCELERATION_5M", side,
    from_ms: a.at_ms, to_ms: c.at_ms,
    from_price: a.price, to_price: c.price,
    available_at_ms: d.confirmed_at_ms,
    trend_version: main.trend_version,
    classification: "UNVALIDATED_GEOMETRY_ONLY",
    pivots: four.map(p => ({ ...p })) as unknown as ReplayAcceleration["pivots"],
    target_price_at_fourth: targetPrice,
    distance_to_target: distance,
  };
}

/** Single pass over closed M5 only. No lookahead and no backpainting. */
export function accelerationGeometryTimeline(document: ReplayDocument): ReplayAcceleration[] {
  if (document.mode !== "MARKET_ONLY") return [];
  const mainAndTarget = (document.geometry ?? []).filter(line =>
    line.kind === "MAIN_1H" || line.kind === "TARGET_1H");
  const breaks = document.hourly_prior_breaks ?? [];
  const result: ReplayAcceleration[] = [];
  const bars: ReplayCandle[] = [];
  const pivots: EarlyPivot[] = [];
  const emitted = new Set<string>();
  let main: ReplayGeometry | null = null, target: ReplayGeometry | null = null;
  let active: ReplayAcceleration | null = null;
  let lineIndex = 0, breakIndex = 0;
  for (const event of document.events) {
    if (event.kind !== "CANDLE_CLOSED" || !event.candle) continue;
    const bar = event.candle;
    if (bars.length && bars.at(-1)!.end_ms !== bar.start_ms) {
      bars.length = 0; pivots.length = 0; active = null;
    }
    bars.push(bar);
    appendEarlyPivot(bars, pivots);
    while (lineIndex < mainAndTarget.length &&
           mainAndTarget[lineIndex].available_at_ms <= event.time_ms) {
      const line = mainAndTarget[lineIndex++];
      if (line.kind === "MAIN_1H") {
        if (main?.trend_version !== line.trend_version) {
          active = null; target = null;
        }
        main = line;
      } else target = line;
    }
    while (breakIndex < breaks.length &&
           breaks[breakIndex].confirmed_at_ms <= event.time_ms) {
      const item = breaks[breakIndex++];
      if (main?.trend_version === item.trend_version) {
        main = null; target = null; active = null;
      }
    }
    if (active && bar.end_ms > active.available_at_ms) {
      const linePrice = projectedPrice(active, bar.end_ms);
      const broken = active.side === "BULL"
        ? bar.close < linePrice : bar.close > linePrice;
      if (broken) {
        active.retired_at_ms = bar.end_ms;
        active = null;
      }
    }
    if (!main || !target || target.trend_version !== main.trend_version ||
        target.side !== main.side || target.available_at_ms > event.time_ms)
      continue;
    const four = pivots.slice(-4);
    if (!isAlignedFour(four, main.side)) continue;
    if (four[3].confirmed_at_ms > event.time_ms ||
        four[3].at_ms < main.available_at_ms) continue;
    const key = [main.trend_version, ...four.map(p => p.at_ms)].join(":");
    if (emitted.has(key)) continue;
    const candidate = fourPivotAcceleration(bars, four, main.side, main, target);
    if (!candidate) continue;
    emitted.add(key);
    if (active) active.superseded_at_ms = candidate.available_at_ms;
    active = candidate;
    result.push(candidate);
  }
  return result;
}

export function visibleAccelerationHistory(
  timeline: readonly ReplayAcceleration[], time: number | null,
): ReplayAcceleration[] {
  if (time === null) return [];
  return timeline.filter(line => line.available_at_ms <= time).map(line =>
    line.retired_at_ms !== undefined && line.retired_at_ms > time
      ? { ...line, retired_at_ms: undefined } : line);
}
