import { describe, expect, it } from "vitest";
import type { ReplayDocument, ReplayEvent } from "./replayModel";
import {
  automaticLineStyle, lastM5AccelerationTimeline, visibleLastM5Accelerations,
} from "./lastM5Acceleration";

const STEP = 300_000;
const START = Date.UTC(2026, 7, 20);
const highs = [99, 100, 101, 103, 105, 108, 106, 104, 103, 105, 107, 111, 109, 108, 105];
const lows = [96, 94, 90, 94, 96, 99, 98, 97, 95, 101, 103, 105, 104, 103, 85];

function archive(side: "BULL" | "BEAR", targetPrice?: number): ReplayDocument {
  const mirror = (n: number) => side === "BULL" ? n : 200 - n;
  const events: ReplayEvent[] = highs.map((hi, i) => {
    const high = side === "BULL" ? hi : mirror(lows[i]);
    const low = side === "BULL" ? lows[i] : mirror(hi);
    const midpoint = (high + low) / 2;
    const close = i === 14 ? (side === "BULL" ? 90 : 110) : midpoint;
    return {
      source: "SIMULATION", simulation_run_id: "accel_fixture",
      sequence: i + 1, kind: "CANDLE_CLOSED",
      time_ms: START + (i + 1) * STEP,
      candle: { start_ms: START + i * STEP, end_ms: START + (i + 1) * STEP,
        open: midpoint, high, low, close, volume: 10 },
    };
  });
  const available_at_ms = events[1].time_ms;
  const parent = { side, classification: "UNVALIDATED_GEOMETRY_ONLY" as const,
    available_at_ms, trend_version: available_at_ms,
    from_ms: START, to_ms: START + STEP };
  const target = targetPrice ?? mirror(110);
  return {
    source: "SIMULATION", simulation_run_id: "accel_fixture",
    mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
    symbol: "GRASSUSDT", timeframe: "5m", events,
    hourly_prior_updates: [], hourly_prior_breaks: [],
    geometry: [
      { ...parent, kind: "MAIN_1H", from_price: mirror(90), to_price: mirror(90) },
      { ...parent, kind: "TARGET_1H", from_price: target, to_price: target },
    ],
  };
}

describe("distinct visual-only last M5 acceleration at H1 target", () => {
  it("publishes only after FOUR M5 confirmed local extrema and exact H1 target contact", () => {
    const doc = archive("BULL");
    const original = JSON.stringify(doc);
    const timeline = lastM5AccelerationTimeline(doc);
    expect(timeline).toHaveLength(1);
    const line = timeline[0];
    expect(line.kind).toBe("ACCELERATION_5M");
    expect(line.classification).toBe("UNVALIDATED_GEOMETRY_ONLY");
    expect(line.side).toBe("BULL");
    expect(line.from_ms).toBe(START + 2 * STEP);
    expect(line.to_ms).toBe(START + 8 * STEP);
    expect(line.from_price).toBe(90);
    expect(line.to_price).toBe(95);
    expect(line.pivot_prices).toEqual([90, 108, 95, 111]);
    expect(line.pivot_times_ms).toEqual([2, 5, 8, 11].map(i => START + i * STEP));
    expect(line.pivot_confirmed_at_ms[3]).toBe(doc.events[13].time_ms);
    expect(line.available_at_ms).toBe(doc.events[13].time_ms);
    expect(line.target_price_at_pivot4).toBe(110);
    expect(line.target_contact).toBe(true);
    expect(visibleLastM5Accelerations(timeline, doc.events[12].time_ms)).toEqual([]);
    expect(visibleLastM5Accelerations(timeline, doc.events[13].time_ms)[0].retired_at_ms).toBeUndefined();
    expect(line.retired_at_ms).toBe(doc.events[14].time_ms);
    expect(visibleLastM5Accelerations(timeline, doc.events[14].time_ms)[0].retired_at_ms).toBe(doc.events[14].time_ms);
    // Source and trade journal are immutable, even when a candidate retires.
    expect(JSON.stringify(doc)).toBe(original);
    expect(doc.events.every(e => e.kind === "CANDLE_CLOSED")).toBe(true);
  });

  it("is symmetric for last bearish M5 leg against falling H1 target", () => {
    const line = lastM5AccelerationTimeline(archive("BEAR"))[0];
    expect(line).toBeDefined();
    expect(line.side).toBe("BEAR");
    expect(line.pivot_prices).toEqual([110, 92, 105, 89]);
    expect(line.from_price).toBe(110);
    expect(line.to_price).toBe(105);
    expect(line.target_price_at_pivot4).toBe(90);
  });

  it("never invents a target proximity radius or a fourth confirmed pivot", () => {
    expect(lastM5AccelerationTimeline(archive("BULL", 112))).toEqual([]);
    const partial = archive("BULL");
    partial.events = partial.events.slice(0, 13);
    expect(lastM5AccelerationTimeline(partial)).toEqual([]);
    const missingH1 = archive("BULL");
    missingH1.geometry = [];
    expect(lastM5AccelerationTimeline(missingH1)).toEqual([]);
  });

  it("renders the acceleration blue DASHED while M5 reference stays solid", () => {
    expect(automaticLineStyle("ACCELERATION_5M")).toEqual({stroke:"#57aaff",dash:[6,4]});
    expect(automaticLineStyle("REFERENCE_5M")).toEqual({stroke:"#57aaff",dash:[]});
    expect(automaticLineStyle("MAIN_1H")).toEqual({stroke:"#f6dc59",dash:[]});
    expect(automaticLineStyle("TARGET_1H")).toEqual({stroke:"#f6dc59",dash:[6,4]});
  });
});
