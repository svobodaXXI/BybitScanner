import { describe, expect, it } from "vitest";
import type { ReplayCandle } from "./replayModel";
import {
  chartLogicalAtTime, drawingLogicalToTime, geometryLogicalSegment, timeAtChartLogical, timeToDrawingLogical,
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
