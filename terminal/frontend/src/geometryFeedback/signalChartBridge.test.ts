import { describe, expect, it } from "vitest";
import { initialSourceGeometryRange, projectSignalGeometry, projectSourceReferenceOnLiveCandles, restoreSavedSignalCorrection } from "./signalChartBridge";
import { serializeReviewDrawings } from "./geometryReviewDraft";

const candles = [
  { time: "2026-10-19T00:00:00.000Z", open: 9, high: 12, low: 8, close: 11 },
  { time: "2026-10-19T00:05:00.000Z", open: 11, high: 13, low: 10, close: 12 },
  { time: "2026-10-19T00:10:00.000Z", open: 12, high: 14, low: 9, close: 10 },
] as const;
const at = (index: number, price: number) => ({
  bar_open_time_ms: Date.parse(candles[index].time), price,
});
const source = [
  { id: "upper", type: "ray" as const, anchors: [at(0, 12), at(2, 14)] },
  { id: "lower", type: "ray" as const, anchors: [at(0, 8), at(2, 9)] },
];

describe("historical editor viewport", () => {
  it("centers the immutable source pivots even if later frozen candles exist", () => {
    const { referenceDrawings } = projectSignalGeometry(source, candles);
    const range = initialSourceGeometryRange(referenceDrawings);
    expect(range).toEqual({ from: -12, to: 14 });
    expect(range!.from).toBeLessThan(referenceDrawings[0].anchors[0].logical);
    expect(range!.to).toBeGreaterThan(referenceDrawings[0].anchors[1].logical);
  });

  it("does not override the chart viewport without anchored source evidence", () => {
    expect(initialSourceGeometryRange([])).toBeNull();
  });
});

describe("GFL frozen signal-to-chart bridge", () => {
  it("projects both immutable rays and makes independent editable copies", () => {
    const { referenceDrawings, editableDrawings } = projectSignalGeometry(source, candles);
    expect(referenceDrawings.map((d) => d.anchors.map((a) => a.logical))).toEqual([[0, 2], [0, 2]]);
    expect(referenceDrawings.every((d) => d.locked)).toBe(true);
    expect(editableDrawings.every((d) => !d.locked)).toBe(true);
    editableDrawings[0].anchors[0].price = 11.5;
    expect(referenceDrawings[0].anchors[0].price).toBe(12);
    expect(serializeReviewDrawings(referenceDrawings, candles)[0].anchors).toEqual(source[0].anchors);
  });

  it("fails closed if an anchor candle is missing; never snaps to a neighbor", () => {
    expect(() => projectSignalGeometry(source, candles.slice(1))).toThrow(/absent/);
    expect(() => projectSignalGeometry([{ ...source[0], anchors: [{ ...source[0].anchors[0], bar_open_time_ms: at(0, 12).bar_open_time_ms + 1 }, source[0].anchors[1]] }], candles)).toThrow(/absent/);
  });

  it("rejects zero-length and backward Scanner ray anchors instead of projecting misleading lines", () => {
    expect(() => projectSignalGeometry([
      { ...source[0], anchors: [at(1, 12), at(1, 13)] },
    ], candles)).toThrow(/advance/);
    expect(() => projectSignalGeometry([
      { ...source[0], anchors: [at(2, 14), at(0, 12)] },
    ], candles)).toThrow(/advance/);
    expect(projectSignalGeometry(source, candles).editableDrawings).toHaveLength(2);
  });

  it("rejects malformed candles, duplicate IDs, incomplete rays, and invalid prices", () => {
    expect(() => projectSignalGeometry(source, [candles[1], candles[0]])).toThrow();
    expect(() => projectSignalGeometry(source, [candles[0], candles[0]])).toThrow();
    expect(() => projectSignalGeometry([source[0], source[0]], candles)).toThrow();
    expect(() => projectSignalGeometry([{ ...source[0], anchors: [source[0].anchors[0]] }], candles)).toThrow();
    expect(() => projectSignalGeometry([{ ...source[0], anchors: [at(0, -1), at(2, 14)] }], candles)).toThrow();
  });
});


describe("persisted Editor correction restores by frozen boundary identity", () => {
  const references = projectSignalGeometry(source, candles).referenceDrawings;
  const changedUpper = { ...source[0], anchors: [at(0, 11.25), at(2, 13.5)] };
  const changedLower = { ...source[1], anchors: [at(0, 8.25), at(2, 9.5)] };

  it("accepts reversed canonical store order without swapping owner lines", () => {
    const owner = restoreSavedSignalCorrection(references, [changedLower, changedUpper], candles);
    expect(owner.map((line) => line.id)).toEqual(["editable:upper", "editable:lower"]);
    expect(owner.map((line) => line.anchors[0].price)).toEqual([11.25, 8.25]);
    expect(owner.every((line) => line.locked === false)).toBe(true);
    expect(references.map((line) => line.anchors[0].price)).toEqual([12, 8]);
    const savedAgain = serializeReviewDrawings(
      owner.map((line) => ({ ...line, id: line.id.slice("editable:".length) })), candles,
    );
    expect(savedAgain.map((line) => line.id)).toEqual(["upper", "lower"]);
    expect(savedAgain[0].anchors).toEqual(changedUpper.anchors);
    expect(savedAgain[1].anchors).toEqual(changedLower.anchors);
  });

  it("rejects missing, duplicate, foreign, wrong-kind and corrupted saved rays", () => {
    const invalid = [
      [changedUpper],
      [changedUpper, changedUpper],
      [changedUpper, { ...changedLower, id: "other" }],
      [changedUpper, { ...changedLower, type: "trend" as const }],
      [changedUpper, { ...changedLower, anchors: [at(0, 8), at(2, -1)] }],
      [changedUpper, { ...changedLower, anchors: [at(2, 9), at(0, 8)] }],
      [changedUpper, { ...changedLower, anchors: [at(0, 8), {
        bar_open_time_ms: at(1, 9).bar_open_time_ms + 1, price: 9,
      }] }],
    ];
    for (const review of invalid)
      expect(() => restoreSavedSignalCorrection(references, review, candles)).toThrow();
    expect(() => restoreSavedSignalCorrection(references, [changedUpper, changedLower],
      candles.slice(1))).toThrow(/absent/);
  });
});


describe("retrospective Editor candles", () => {
  it("appends contiguous later closed OHLC without changing original source geometry", async () => {
    const { appendRetrospectiveCandles } = await import("./signalChartBridge");
    const original = [...candles];
    const asof = Date.parse(candles[2].time) + 600000;
    const later = [
      { open_time_ms: asof - 300000, open: 10, high: 13, low: 9, close: 12 },
      { open_time_ms: asof, open: 12, high: 15, low: 11, close: 14 },
    ];
    const extended = appendRetrospectiveCandles(candles, later, "5m", asof);
    expect(extended).toHaveLength(5);
    expect(original).toEqual(candles);
    expect(projectSignalGeometry(source, extended).referenceDrawings.map((line) => line.anchors.map((a) => a.logical)))
      .toEqual([[0, 2], [0, 2]]);
    expect(() => appendRetrospectiveCandles(candles, [later[1]], "5m", asof)).toThrow();
    expect(() => appendRetrospectiveCandles(candles, later, "1h", asof)).toThrow();
  });
});

describe("Autopilot immutable signal overlay on live candles", () => {
  const original = projectSignalGeometry(source, candles).referenceDrawings;
  it("reuses exact timestamps and immutable prices on an extended live chart", () => {
    const live = [
      { time: "2026-10-18T23:55:00.000Z", open: 10, high: 11, low: 9, close: 10 },
      ...candles.map((bar) => ({ ...bar, close: bar.close + 0.5 })),
      { time: "2026-10-19T00:15:00.000Z", open: 10, high: 12, low: 9, close: 11 },
    ];
    const aligned = projectSourceReferenceOnLiveCandles(original, candles, live);
    expect(aligned?.map((line) => line.anchors.map((a) => a.logical))).toEqual([[1, 3], [1, 3]]);
    expect(aligned?.map((line) => line.anchors.map((a) => a.price))).toEqual([[12, 14], [8, 9]]);
    expect(aligned?.every((line) => line.locked)).toBe(true);
    expect(original.map((line) => line.anchors[0].logical)).toEqual([0, 0]);
  });
  it("does not invent anchors for stale, missing, or disordered live candles", () => {
    expect(projectSourceReferenceOnLiveCandles(original, candles, candles.slice(1))).toBeNull();
    expect(projectSourceReferenceOnLiveCandles(original, candles, [])).toBeNull();
    expect(projectSourceReferenceOnLiveCandles(original, candles, [...candles].reverse())).toBeNull();
    expect(projectSourceReferenceOnLiveCandles([], candles, candles)).toBeNull();
  });
});
