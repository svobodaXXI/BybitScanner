/**
 * Last five-minute acceleration: VISUAL-ONLY, counter-H1-target-touch study.
 *
 * Unlike the with-H1-trend blue REFERENCE_5M, this uses the most recent
 * confirmed four local M5 pivots in the H1 direction, numbered 1→2→3→4,
 * with a 1→3 wick-tight boundary. Four-pivot evidence and exact H1 target
 * contact are deliberate conservative prerequisites. The owner's optional
 * forming point 4 and undefined "near" tolerance are NOT simulated.
 *
 * No entries, trading events, numeric acceleration threshold, risk gate,
 * PAPER data or replay archive mutations are produced here.
 */
import {
  appendEarlyPivot, visiblePriorBreaks, wickTightEarlySlope,
  type EarlyPivot, type ReplayCandle, type ReplayDocument, type ReplayGeometry,
} from "./replayModel";

export type LastM5Acceleration = {
  kind: "ACCELERATION_5M";
  side: "BULL" | "BEAR";
  available_at_ms: number;
  from_ms: number; to_ms: number; from_price: number; to_price: number;
  trend_version: number;
  pivot_times_ms: [number, number, number, number];
  pivot_prices: [number, number, number, number];
  pivot_confirmed_at_ms: [number, number, number, number];
  target_price_at_pivot4: number;
  target_contact: true;
  retired_at_ms?: number;
  classification: "UNVALIDATED_GEOMETRY_ONLY";
};

const expectedStructure = (p: readonly EarlyPivot[], side: "BULL" | "BEAR"): boolean => {
  if (p.length !== 4) return false;
  const [a, b, c, d] = p;
  return side === "BULL"
    ? a.kind === "LOW" && b.kind === "HIGH" && c.kind === "LOW" &&
      d.kind === "HIGH" && c.price > a.price && d.price > b.price
    : a.kind === "HIGH" && b.kind === "LOW" && c.kind === "HIGH" &&
      d.kind === "LOW" && c.price < a.price && d.price < b.price;
};

const valueAt = (line: ReplayGeometry | LastM5Acceleration, ms: number) =>
  line.from_price + (line.to_price - line.from_price) *
    (ms - line.from_ms) / (line.to_ms - line.from_ms);

export function lastM5AccelerationTimeline(document: ReplayDocument): LastM5Acceleration[] {
  if (document.mode !== "MARKET_ONLY" || !document.geometry?.length) return [];
  const closed = document.events.filter(e => e.kind === "CANDLE_CLOSED" && e.candle);
  if (!closed.length) return [];
  const lastMs = closed.at(-1)!.time_ms;
  const breaks = visiblePriorBreaks(document, lastMs);
  const lines = document.geometry;
  const history: LastM5Acceleration[] = [];
  const seenVersions = new Set<string>();
  const brokenVersions = new Set<number>();
  const bars: ReplayCandle[] = [];
  const pivots: EarlyPivot[] = [];
  let main: ReplayGeometry | undefined;
  let target: ReplayGeometry | undefined;
  let geometryIndex = 0;
  let breakIndex = 0;
  let active: LastM5Acceleration | undefined;

  for (const event of closed) {
    const candle = event.candle!;
    if (bars.length && bars.at(-1)!.end_ms !== candle.start_ms) {
      bars.length = 0; pivots.length = 0;
      if (active && active.retired_at_ms === undefined)
        active.retired_at_ms = event.time_ms;
      active = undefined;
    }
    bars.push(candle);
    appendEarlyPivot(bars, pivots);
    while (geometryIndex < lines.length &&
           lines[geometryIndex].available_at_ms <= event.time_ms) {
      const line = lines[geometryIndex++];
      if (line.kind === "MAIN_1H") main = line;
      if (line.kind === "TARGET_1H") target = line;
    }
    while (breakIndex < breaks.length && breaks[breakIndex].confirmed_at_ms <= event.time_ms) {
      brokenVersions.add(breaks[breakIndex++].trend_version);
    }
    const hourlyActive = main && target && main.trend_version === target.trend_version &&
      main.side === target.side && !brokenVersions.has(target.trend_version);
    if (active && event.time_ms > active.available_at_ms &&
        active.retired_at_ms === undefined) {
      const sameMovement = hourlyActive && active.trend_version === target!.trend_version;
      // Closed-bar counter-H1 move, NOT an entry signal.
      const broken = active.side === "BULL"
        ? candle.close < valueAt(active, candle.end_ms)
        : candle.close > valueAt(active, candle.end_ms);
      if (!sameMovement || broken) {
        active.retired_at_ms = event.time_ms;
        active = undefined;
      }
    }
    if (!hourlyActive || !target) continue;
    const four = pivots.slice(-4);
    if (!expectedStructure(four, target.side)) continue;
    const [a, b, c, d] = four;
    if (target.available_at_ms > d.at_ms ||
        d.confirmed_at_ms > event.time_ms) continue;
    const targetAtPoint4 = valueAt(target, d.at_ms);
    // Exact contact, with NO invented proximity threshold.
    const touched = target.side === "BULL"
      ? d.price >= targetAtPoint4 : d.price <= targetAtPoint4;
    if (!touched) continue;
    const candidate = wickTightEarlySlope(
      bars, a, c, target.side, event.time_ms, "ACCELERATION_5M",
    );
    if (!candidate) continue;
    const key = [target.trend_version, a.at_ms, b.at_ms, c.at_ms, d.at_ms,
      a.price, b.price, c.price, d.price, candidate.to_ms, candidate.to_price].join(":");
    if (seenVersions.has(key)) continue;
    seenVersions.add(key);
    const version: LastM5Acceleration = {
      ...candidate,
      kind: "ACCELERATION_5M",
      trend_version: target.trend_version,
      // This is the publication close, NOT the anchor's older candle.
      available_at_ms: event.time_ms,
      pivot_times_ms: [a.at_ms, b.at_ms, c.at_ms, d.at_ms],
      pivot_prices: [a.price, b.price, c.price, d.price],
      pivot_confirmed_at_ms: [
        a.confirmed_at_ms, b.confirmed_at_ms, c.confirmed_at_ms, d.confirmed_at_ms,
      ],
      target_price_at_pivot4: targetAtPoint4,
      target_contact: true,
      classification: "UNVALIDATED_GEOMETRY_ONLY",
    };
    history.push(version);
    active = version;
  }
  return history;
}

export function visibleLastM5Accelerations(
  timeline: readonly LastM5Acceleration[], closedTimeMs: number | null,
): LastM5Acceleration[] {
  if (closedTimeMs === null) return [];
  return timeline.filter(line => line.available_at_ms <= closedTimeMs).map(line =>
    line.retired_at_ms !== undefined && line.retired_at_ms > closedTimeMs
      ? { ...line, retired_at_ms: undefined } : { ...line });
}

/** Style contract shared with the chart renderer and regression tests. */
export function automaticLineStyle(kind: ReplayGeometry["kind"] | "ACCELERATION_5M") {
  return {
    stroke: kind === "REFERENCE_5M" || kind === "ACCELERATION_5M"
      ? "#57aaff" : "#f6dc59",
    dash: kind === "TARGET_1H" || kind === "ACCELERATION_5M" ? [6, 4] : [],
  };
}
