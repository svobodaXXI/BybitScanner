import { describe, expect, it } from "vitest";
import { projectSignalGeometry } from "./signalChartBridge";
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
