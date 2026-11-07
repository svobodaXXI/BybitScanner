import { describe, expect, it } from "vitest";
import type { ReplayCandle, ReplayDocument, ReplayGeometry } from "./replayModel";
import { accelerationGeometryTimeline, visibleAccelerationHistory } from "./replayAcceleration";

const step = 300_000, t = Date.UTC(2026, 7, 20);
const ranges = [
  [96, 93], [95, 92], [94, 90], [97, 94],
  [101, 96], [104, 100], [102, 97], [99, 95],
  [98, 94], [100, 96], [104, 100], [109, 104],
  [105, 100], [103, 98], [105, 90], [100, 95],
] as const;

function document(side: "BULL"|"BEAR" = "BULL", targetPrice = 109): ReplayDocument {
  const transform = (high: number, low: number) => side === "BULL"
    ? [high, low] : [200 - low, 200 - high];
  const candles: ReplayCandle[] = ranges.map(([high, low], i) => {
    const [h, l] = transform(high, low);
    return {
      start_ms: t + i * step, end_ms: t + (i + 1) * step,
      open: (h+l)/2, high: h, low: l,
      close: i === 14 ? (side === "BULL" ? 90 : 110) : (h+l)/2,
      volume: 1,
    };
  });
  const available = t + step;
  const base: Omit<ReplayGeometry,"kind"> = {
    side, available_at_ms: available, from_ms: t, to_ms: t + 3 * step,
    from_price: side === "BULL" ? 90 : 110,
    to_price: side === "BULL" ? 92 : 108,
    trend_version: available,
    classification: "UNVALIDATED_GEOMETRY_ONLY",
  };
  const target: ReplayGeometry = {
    ...base, kind: "TARGET_1H", from_price: side === "BULL" ? targetPrice : 200 - targetPrice,
    to_price: side === "BULL" ? targetPrice : 200 - targetPrice,
  };
  return {
    source: "SIMULATION", mode: "MARKET_ONLY",
    simulation_run_id: "accel_fixture", symbol: "GRASSUSDT", timeframe: "5m",
    events: candles.map((candle,i) => ({
      source: "SIMULATION" as const, simulation_run_id: "accel_fixture",
      kind: "CANDLE_CLOSED" as const, sequence: i+1, time_ms: candle.end_ms, candle,
    })),
    geometry: [{...base,kind:"MAIN_1H"},target],
  };
}

describe("M5 last-acceleration research overlay (not continuation blue)", () => {
  it("waits for four significant closed M5 pivots, near H1 target requires actual touch", () => {
    const doc = document();
    expect(accelerationGeometryTimeline({...doc,events:doc.events.slice(0,13)})).toEqual([]);
    const history = accelerationGeometryTimeline({...doc,events:doc.events.slice(0,14)});
    expect(history).toHaveLength(1);
    const line = history[0];
    expect(line.kind).toBe("ACCELERATION_5M");
    expect(line.pivots.map(p => p.kind)).toEqual(["LOW","HIGH","LOW","HIGH"]);
    expect(line.pivots.map(p => p.price)).toEqual([90,104,94,109]);
    expect(line.from_ms).toBe(t + 2*step);
    expect(line.to_ms).toBe(t + 8*step);
    expect(line.available_at_ms).toBe(t + 14*step);
    expect(line.target_price_at_fourth).toBe(109);
    expect(line.distance_to_target).toBe(0);
    expect(visibleAccelerationHistory(history,t+13*step)).toEqual([]);
    expect(visibleAccelerationHistory(history,t+14*step)).toHaveLength(1);
    expect(visibleAccelerationHistory(history,null)).toEqual([]);
    // Do not invent a "near target" number; a one-point gap is not yet approved.
    expect(accelerationGeometryTimeline(document("BULL",110))).toEqual([]);
  });

  it("retains dashed-only acceleration after its CLOSED M5 break and on rewind", () => {
    const history = accelerationGeometryTimeline(document());
    expect(history).toHaveLength(1);
    const line = history[0];
    expect(line.retired_at_ms).toBe(t+15*step);
    expect(visibleAccelerationHistory(history,t+14*step)[0].retired_at_ms).toBeUndefined();
    expect(visibleAccelerationHistory(history,t+15*step)[0].retired_at_ms).toBe(t+15*step);
    expect(visibleAccelerationHistory(history,t+16*step)).toHaveLength(1);
    expect(visibleAccelerationHistory(history,t+13*step)).toEqual([]);
  });

  it("builds descending structure symmetrically against H1 BEAR", () => {
    const history = accelerationGeometryTimeline(document("BEAR"));
    expect(history).toHaveLength(1);
    expect(history[0].side).toBe("BEAR");
    expect(history[0].pivots.map(p => p.kind)).toEqual(["HIGH","LOW","HIGH","LOW"]);
    expect(history[0].pivots.map(p => p.price)).toEqual([110,96,106,91]);
    expect(history[0].from_price).toBe(110);
    expect(history[0].to_price).toBe(106);
    expect(history[0].retired_at_ms).toBe(t+15*step);
  });

  it("ignores missing H1 target, inactive H1 main and unrelated trades", () => {
    const doc = document();
    expect(accelerationGeometryTimeline({...doc, geometry:doc.geometry?.slice(0,1)})).toEqual([]);
    expect(accelerationGeometryTimeline({...doc,geometry:[]})).toEqual([]);
    const priorBreak = {
      kind: "PRIOR_CLOSE_NEXT_OPEN" as const, previous_side: "BULL" as const,
      new_side: "BEAR" as const, confirmed_at_ms: t+10*step,
      trend_version: t+step, prior_price: 90, prior_at_ms: t,
      hourly_close_ms: t+9*step, next_hour_open_ms: t+9*step,
    };
    expect(accelerationGeometryTimeline({...doc,hourly_prior_breaks:[priorBreak]})).toEqual([]);
    expect(doc.events.every(e=>e.kind==="CANDLE_CLOSED")).toBe(true);
  });
});
