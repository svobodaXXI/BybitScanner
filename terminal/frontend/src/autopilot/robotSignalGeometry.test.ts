import { describe, expect, it } from "vitest";
import { parseProvenRobotSignalGeometry, robotSignalTimeframeMatchesChart } from "./robotSignalGeometry";

const origin = {
  pattern: "Falling Wedge", candidate_id: "candidate-btc",
  signal_timeframe_minutes: 5, mirror_campaign: false,
  mirror_level_source: null, mirror_pattern: null, reentry_attempt_index: null,
};
const first = Date.UTC(2026, 10, 9, 10);
const second = first + 300_000;
const snapshot = {
  ok: true,
  snapshot: {
    schema_version: 1, signal_id: "candidate-btc", symbol: "BTCUSDT", timeframe: "5",
    bars: [
      { open_time_ms: first, open: 100, high: 103, low: 99, close: 101 },
      { open_time_ms: second, open: 101, high: 104, low: 100, close: 103 },
    ],
    boundaries: [{
      boundary_id: "exact-ray", kind: "ray",
      anchors: [
        { bar_open_time_ms: first, price: 100 },
        { bar_open_time_ms: second, price: 101 },
      ],
    }],
  },
};
const expected = { candidateId: "candidate-btc", symbol: "BTCUSDT", origin };

describe("exact-source Robot geometry", () => {
  it("accepts only archived Scanner pivots for the selected immutable Robot candidate", () => {
    expect(parseProvenRobotSignalGeometry(snapshot, expected)).toEqual([{
      id: "exact-ray", type: "ray", anchors: [
        { bar_open_time_ms: first, price: 100 },
        { bar_open_time_ms: second, price: 101 },
      ],
    }]);
    expect(robotSignalTimeframeMatchesChart(origin, "5m")).toBe(true);
    expect(robotSignalTimeframeMatchesChart(origin, "1m")).toBe(false);
    expect(robotSignalTimeframeMatchesChart(origin, "15s")).toBe(false);
  });

  it("rejects wrong candidate, symbol, timeframe or missing original archive", () => {
    expect(parseProvenRobotSignalGeometry(snapshot, { ...expected, candidateId: "other" })).toBeNull();
    expect(parseProvenRobotSignalGeometry({ ...snapshot, snapshot: {
      ...snapshot.snapshot, signal_id: "other",
    } }, expected)).toBeNull();
    expect(parseProvenRobotSignalGeometry({ ...snapshot, snapshot: {
      ...snapshot.snapshot, symbol: "ETHUSDT",
    } }, expected)).toBeNull();
    expect(parseProvenRobotSignalGeometry({ ...snapshot, snapshot: {
      ...snapshot.snapshot, timeframe: "1",
    } }, expected)).toBeNull();
    expect(parseProvenRobotSignalGeometry({ ok: false }, expected)).toBeNull();
  });

  it("never fabricates, reorders or clamps invalid signal anchors", () => {
    expect(parseProvenRobotSignalGeometry({
      ...snapshot, snapshot: { ...snapshot.snapshot, boundaries: [{
        ...snapshot.snapshot.boundaries[0],
        anchors: [{ bar_open_time_ms: first - 300_000, price: 100 },
          { bar_open_time_ms: second, price: 101 }],
      }] },
    }, expected)).toBeNull();
    expect(parseProvenRobotSignalGeometry({
      ...snapshot, snapshot: { ...snapshot.snapshot, boundaries: [{
        ...snapshot.snapshot.boundaries[0],
        anchors: [{ bar_open_time_ms: second, price: 100 },
          { bar_open_time_ms: first, price: 101 }],
      }] },
    }, expected)).toBeNull();
    expect(parseProvenRobotSignalGeometry({
      ...snapshot, snapshot: { ...snapshot.snapshot, boundaries: [{
        ...snapshot.snapshot.boundaries[0],
        anchors: [{ bar_open_time_ms: first, price: Number.NaN },
          { bar_open_time_ms: second, price: 101 }],
      }] },
    }, expected)).toBeNull();
  });
});
