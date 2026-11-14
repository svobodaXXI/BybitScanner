import { describe, expect, it } from "vitest";
import { chartWilderDmi } from "./replayChartDmi";
import type { ReplayCandle } from "./replayModel";

const five = 300_000;
const base = Date.UTC(2026, 10, 9, 8);
const candle = (i: number): ReplayCandle => {
  const open = 100 + Math.sin(i / 7) * 6 + i * 0.05;
  const close = open + Math.cos(i / 3) * 0.7;
  return { start_ms: base + i * five, end_ms: base + (i + 1) * five,
    open, close, high: Math.max(open, close) + 1.1 + i % 3 / 10,
    low: Math.min(open, close) - 0.9, volume: 100 };
};

describe("closed M5 display Wilder DMI regression", () => {
  it("recovers +DI, -DI and ADX after 28 closed historical candles", () => {
    const bars = Array.from({ length: 288 }, (_, i) => candle(i));
    const points = chartWilderDmi(bars);
    expect(points).toHaveLength(288);
    expect(points.slice(0, 14).every(p => p.plus_di === null && p.adx === null)).toBe(true);
    expect(points[14].plus_di).not.toBeNull();
    expect(points[26].adx).toBeNull();
    expect(points[27].adx).not.toBeNull();
    expect(points[287].adx).toBeGreaterThan(0);
    expect(points[287].minus_di).toBeGreaterThanOrEqual(0);
    expect(points[287].plus_di).toBeGreaterThanOrEqual(0);
  });
  it("does not leak a future closed M5 into the displayed indicator", () => {
    const bars = Array.from({ length: 45 }, (_, i) => candle(i));
    const before = chartWilderDmi(bars.slice(0, 40));
    const extended = chartWilderDmi(bars);
    expect(extended.slice(0, 40)).toEqual(before);
  });
  it("rejects missing M5 rather than silently computing wrong ADX", () => {
    const bars = Array.from({ length: 40 }, (_, i) => candle(i));
    bars.splice(10, 1);
    expect(() => chartWilderDmi(bars)).toThrow(/contiguous/);
  });
});
