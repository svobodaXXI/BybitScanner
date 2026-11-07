import { describe, expect, it } from "vitest";
import type { ReplayCandle } from "./replayModel";
import {
  automaticGeometryTimeframeCap, chartLogicalAtTime, chartXAtCandleTime, drawingLogicalToTime, geometryLogicalSegment, isLeftEdgeHistoricalFragment, nearestReplayHighLowAnchor, shortActiveM5Ray, timeAtChartLogical, timeToDrawingLogical, wickTightH1MainProjection,
} from "./replayDrawingCoordinates";

const start = Date.UTC(2026, 10, 2);
const mkBar = (i: number, minutes = 5): ReplayCandle => ({
  start_ms: start + i * minutes * 60_000,
  end_ms: start + (i + 1) * minutes * 60_000,
  open: 100, high: 102, low: 99, close: 101, volume: 10,
});
describe("manual replay UTC drawing anchors", () => {
  it("uses the same absolute time when projected onto M5 and completed H1", () => {
    const five = Array.from({ length: 36 }, (_, i) => mkBar(i));
    const hour = Array.from({ length: 3 }, (_, i) => mkBar(i, 60));
    const time = start + 25 * 300_000;
    const anchor = timeToDrawingLogical(time);
    expect(drawingLogicalToTime(anchor)).toBe(time);
    expect(chartLogicalAtTime(time, five)).toBe(25);
    expect(chartLogicalAtTime(time, hour)).toBeCloseTo(25 / 12);
    expect(timeAtChartLogical(chartLogicalAtTime(time, five)!, five)).toBe(time);
    expect(timeAtChartLogical(chartLogicalAtTime(time, hour)!, hour)).toBe(time);
    // A rewind removes visible candles, not the owner's manual anchor.
    expect(timeToDrawingLogical(time)).toBe(anchor);
    expect(chartLogicalAtTime(time, five.slice(0, 12))).toBe(25);
  });
  it("keeps retired five-minute geometry visible inside one H1 candle", () => {
    const hourly = [mkBar(0, 60), mkBar(1, 60), mkBar(2, 60)];
    const five = Array.from({ length: 36 }, (_, i) => mkBar(i));
    const firstMs = start + 10 * 300_000;
    const retiredMs = start + 11 * 300_000;
    const line = { from_ms: firstMs, retired_at_ms: retiredMs };
    const hourSegment = geometryLogicalSegment(line, hourly);
    expect(hourSegment).not.toBeNull();
    expect(hourSegment!.from).toBeCloseTo(10 / 12);
    expect(hourSegment!.to).toBeCloseTo(11 / 12);
    expect(hourSegment!.to).toBeGreaterThan(hourSegment!.from);
    // After a same-direction H1 revision, the prior yellow slope remains
    // reviewable at its original anchors but no longer projects indefinitely
    // across later candles. Rewind hides the future supersession.
    const revisedAt = start + 100 * 60_000;
    const original = { from_ms: firstMs };
    const oldVersion = { ...original, superseded_at_ms: revisedAt };
    expect(geometryLogicalSegment(original, hourly)!.to).toBe(3);
    expect(geometryLogicalSegment(oldVersion, hourly)!.to).toBeCloseTo(100 / 60);
    expect(geometryLogicalSegment(oldVersion, five)!.to).toBeCloseTo(100 / 5);
    expect(geometryLogicalSegment(original, hourly.slice(0, 1))!.to).toBe(1);
    const fiveSegment = geometryLogicalSegment(line, five);
    expect(fiveSegment).toEqual({ from: 10, to: 11 });
    // Later candles never erase or extend the same retired historical line.
    expect(geometryLogicalSegment(line, hourly.slice(0, 2))).toEqual(hourSegment);
    expect(geometryLogicalSegment(line, hourly.slice(0, 1))).toEqual(hourSegment);
    expect(geometryLogicalSegment(line, [])).toBeNull();
    expect(geometryLogicalSegment({ from_ms: firstMs }, hourly.slice(0, 1))!.to)
      .toBeCloseTo(1);
    // No future retirement may be painted beyond the last closed bar.
    expect(geometryLogicalSegment({ from_ms: firstMs, retired_at_ms: start + 5 * 3_600_000 }, hourly.slice(0, 1))!.to).toBeCloseTo(1);
  });

  it("projects M5 timestamps through REAL H1 bar x positions, without rounding", () => {
    const bars = Array.from({ length: 8 }, (_, i) => mkBar(i, 60));
    // The chart has already determined the absolute pixels for each H1 bar.
    const nativeX = (timeMs: number) => {
      const barIndex = bars.findIndex(bar => bar.start_ms === timeMs);
      return barIndex >= 0 ? 110 + barIndex * 9 : null;
    };
    expect(chartXAtCandleTime(start + 2 * 3_600_000 + 30 * 60_000,
      bars, nativeX)).toBeCloseTo(132.5);
    expect(chartXAtCandleTime(start + 5 * 3_600_000, bars, nativeX)).toBe(155);
    expect(chartXAtCandleTime(start + 8 * 3_600_000, bars, nativeX)).toBe(182);
    expect(chartXAtCandleTime(start - 30 * 60_000, bars, nativeX)).toBeCloseTo(105.5);
    expect(chartXAtCandleTime(start, bars.slice(0, 1), nativeX)).toBeNull();
    expect(chartXAtCandleTime(start, bars, () => null)).toBeNull();
    expect(chartXAtCandleTime(Number.NaN, bars, nativeX)).toBeNull();

    // Actual H1 candles may have a gap. Interpolation is based on the
    // underlying timestamps, not invented bars in that gap.
    const withGap = [bars[0], bars[1], bars[4], bars[5]];
    expect(chartXAtCandleTime(start + 2 * 3_600_000,
      withGap, time => ({ [bars[0].start_ms]: 10,
        [bars[1].start_ms]: 20, [bars[4].start_ms]: 50,
        [bars[5].start_ms]: 60 } as Record<number,number>)[time] ?? null)).toBe(30);
  });

  it("tightens only the H1 main ray onto an already-closed protruding wick", () => {
    const hour = 3_600_000;
    const hours = [
      mkBar(0, 60), mkBar(1, 60), mkBar(2, 60),
      mkBar(3, 60), mkBar(4, 60), mkBar(5, 60),
    ];
    // Published BULL 1-3: 100 -> 110 by hour 3. A later green H1
    // wick at hour 4 drops below the extrapolated boundary.
    const line = {
      kind: "MAIN_1H", side: "BULL" as const,
      from_ms: start, to_ms: start + 3 * hour,
      from_price: 100, to_price: 110,
    };
    const bars = hours.map((bar, i) => ({
      ...bar,
      low: [100, 103.5, 107, 110, 112, 117][i],
      high: [104, 108, 112, 115, 119, 122][i],
    }));
    const before = wickTightH1MainProjection(line, bars.slice(0, 4),
      start + 4 * hour);
    expect(before.adjusted).toBe(false);
    const after = wickTightH1MainProjection(line, bars.slice(0, 5),
      start + 5 * hour);
    expect(after.adjusted).toBe(true);
    expect(after.to_ms).toBe(start + 4 * hour);
    expect(after.to_price).toBe(112);
    const slope = (after.to_price - after.from_price) /
      (after.to_ms - after.from_ms);
    for (const bar of bars.slice(1, 5))
      expect(after.from_price + slope * (bar.start_ms - start)).toBeLessThanOrEqual(bar.low);
    expect(wickTightH1MainProjection(line, bars, start + 4 * hour))
      .toEqual(before); // A future wick cannot affect the older replay cursor.
    expect(line.to_ms).toBe(start + 3 * hour);
    expect(line.to_price).toBe(110); // Structural pivot 3 is immutable.
    // A real version published at hour 4 cannot be re-fitted by an hour-4
    // wick closing at hour 5. This is the owner's "no new lower low / higher
    // high = no new slope" scenario, even when the candle crosses the line.
    const published = { ...line, available_at_ms: start + 4 * hour };
    const frozen = wickTightH1MainProjection(published, bars.slice(0, 4),
      start + 4 * hour);
    expect(frozen.adjusted).toBe(false);
    expect(wickTightH1MainProjection(published, bars, start + 6 * hour))
      .toEqual(frozen);
    // When the detector actually publishes a NEW four-pivot version, it
    // may incorporate the then-closed protruding wick. No retroactive move.
    const revised = { ...published, available_at_ms: start + 5 * hour };
    expect(wickTightH1MainProjection(revised, bars, start + 5 * hour))
      .toEqual(after);
    const target = { ...line, kind: "TARGET_1H" };
    expect(wickTightH1MainProjection(target, bars, start + 6 * hour).adjusted)
      .toBe(false);
    // Symmetric bearish upper resistance is tightened upward by a wick.
    const bearish = { ...line, side: "BEAR" as const,
      from_price: 120, to_price: 108 };
    const highs = bars.map((bar, i) => ({
      ...bar, high: [120, 117, 114, 108, 109, 104][i],
    }));
    const bear = wickTightH1MainProjection(bearish, highs.slice(0, 5),
      start + 5 * hour);
    expect(bear.adjusted).toBe(true);
    expect(bear.to_ms).toBe(start + 4 * hour);
    expect(bear.to_price).toBe(109);
  });

  it("ends active M5 ray slightly beyond the last price candle, not chart edge", () => {
    expect(shortActiveM5Ray({ x: 120, y: 80 }, { x: 200, y: 120 },
      300, 960)).toEqual({ x: 336, y: 188 });
    expect(shortActiveM5Ray({ x: 120, y: 80 }, { x: 200, y: 120 },
      900, 960)).toEqual({ x: 936, y: 488 });
    expect(shortActiveM5Ray({ x: 120, y: 80 }, { x: 120, y: 120 },
      300, 960)).toEqual({ x: 120, y: 120 });
  });

  it("caps M5 slopes on H1 at their real publication, never on native M5", () => {
    const published = start + 6 * 3_600_000;
    const m5 = { kind: "REFERENCE_5M" as const, available_at_ms: published };
    const acceleration = { kind: "ACCELERATION_5M" as const, available_at_ms: published };
    const yellow = { kind: "MAIN_1H" as const, available_at_ms: published };
    const target = { kind: "TARGET_1H" as const, available_at_ms: published };
    expect(automaticGeometryTimeframeCap(m5, "1h")).toBe(published);
    expect(automaticGeometryTimeframeCap(acceleration, "1h")).toBe(published);
    expect(automaticGeometryTimeframeCap(m5, "5m")).toBe(Infinity);
    expect(automaticGeometryTimeframeCap(acceleration, "5m")).toBe(Infinity);
    expect(automaticGeometryTimeframeCap(yellow, "1h")).toBe(Infinity);
    expect(automaticGeometryTimeframeCap(target, "1h")).toBe(Infinity);

    const h1 = Array.from({ length: 10 }, (_, i) => mkBar(i, 60));
    const a = start + 2 * 3_600_000 + 10 * 60_000;
    const original = { from_ms: a };
    const capped = geometryLogicalSegment({
      ...original,
      retired_at_ms: Math.min(
        automaticGeometryTimeframeCap(m5, "1h"), h1.at(-1)!.end_ms,
      ),
    }, h1);
    expect(capped?.from).toBeCloseTo(2 + 10 / 60);
    expect(capped?.to).toBe(6);
    expect(geometryLogicalSegment(original, h1)?.to).toBe(10);
    // Neither the archive nor the calculated M5 source coordinates move.
    expect(m5).toEqual({ kind: "REFERENCE_5M", available_at_ms: published });
  });

  it("culls only small retired-line fragments clipped by the left viewport edge", () => {
    expect(isLeftEdgeHistoricalFragment(-250, 25, 1000)).toBe(true);
    expect(isLeftEdgeHistoricalFragment(-250, 119, 1000)).toBe(true);
    expect(isLeftEdgeHistoricalFragment(-250, 160, 1000)).toBe(false);
    expect(isLeftEdgeHistoricalFragment(5, 25, 1000)).toBe(false);
    expect(isLeftEdgeHistoricalFragment(-250, -5, 1000)).toBe(false);
    expect(isLeftEdgeHistoricalFragment(-15, 20, 200)).toBe(true);
    expect(isLeftEdgeHistoricalFragment(-15, 35, 200)).toBe(false);
  });

  it("magnet snaps to selected TF's visible High/Low without changing future data", () => {
    const five = Array.from({ length: 4 }, (_, i) => mkBar(i));
    const toX = (logical: number) => {
      const slot = chartLogicalAtTime(drawingLogicalToTime(logical), five);
      return slot === null ? null : slot * 24;
    };
    const toY = (price: number) => (110 - price) * 10;
    const source = { logical: timeToDrawingLogical(five[2].start_ms) + 0.015, price: 101.8 };
    const snapped = nearestReplayHighLowAnchor(source, five.slice(0, 3), toX, toY);
    expect(snapped).toEqual({ logical: timeToDrawingLogical(five[2].start_ms), price: 102 });
    // Different selected TF: use only completed H1 and retain UTC anchor.
    const hour = [mkBar(0, 60), mkBar(1, 60)];
    const hourAnchor = { logical: timeToDrawingLogical(hour[1].start_ms) + 0.01, price: 99.2 };
    const hourX = (logical: number) => {
      const slot = chartLogicalAtTime(drawingLogicalToTime(logical), hour);
      return slot === null ? null : slot * 30;
    };
    expect(nearestReplayHighLowAnchor(hourAnchor, hour, hourX, toY))
      .toEqual({ logical: timeToDrawingLogical(hour[1].start_ms), price: 99 });
    const future = { logical: timeToDrawingLogical(five[3].start_ms), price: 102 };
    expect(nearestReplayHighLowAnchor(future, five.slice(0, 2), toX, toY))
      .toEqual(future);
    const remote = { logical: timeToDrawingLogical(five[1].start_ms), price: 120 };
    expect(nearestReplayHighLowAnchor(remote, five, toX, toY))
      .toEqual(remote);
  });

  it("preserves actual UTC time across M5 gaps without inventing candles", () => {
    const bars = [mkBar(0), mkBar(1), mkBar(3), mkBar(4)];
    const time = mkBar(2).start_ms;
    const logical = chartLogicalAtTime(time, bars);
    expect(logical).toBe(1.5);
    expect(timeAtChartLogical(logical!, bars)).toBe(time);
    expect(timeAtChartLogical(0, [])).toBeNull();
    expect(chartLogicalAtTime(time, [])).toBeNull();
  });
});
