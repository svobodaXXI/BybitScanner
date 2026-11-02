import { describe, expect, it } from "vitest";
import type { DrawingObject } from "../chart/drawingModel";
import { buildEditorGeometryReview, buildGeometryReviewDraft, compareEditorRayChanges, matchesStoredGeometryReview, serializeReviewDrawings } from "./geometryReviewDraft";

const candles = [
  { time: "2026-10-19T00:00:00.000Z", open: 10, high: 12, low: 9, close: 11 },
  { time: "2026-10-19T00:05:00.000Z", open: 11, high: 13, low: 10, close: 12 },
] as const;
const line: DrawingObject = {
  id: "upper", type: "trend", anchors: [{ logical: 0, price: 12 }, { logical: 1, price: 13 }],
  style: { color: "#fff", lineWidth: 1 }, locked: false, hidden: false,
};
const base = {
  signalId: "signal-1", snapshotRevision: "rev-1", barsSha256: "a".repeat(64),
  frozenCandles: candles, drawings: [line],
} as const;

describe("Geometry Feedback review draft", () => {
  it("converts drawing indices into stable UTC candle-open timestamps", () => {
    expect(serializeReviewDrawings([line], candles)[0].anchors).toEqual([
      { bar_open_time_ms: Date.parse(candles[0].time), price: 12 },
      { bar_open_time_ms: Date.parse(candles[1].time), price: 13 },
    ]);
    expect(buildGeometryReviewDraft({ ...base, label: "GEOMETRY_CORRECTED" }).corrected_boundaries).toHaveLength(1);
  });
  it("fails closed on fractional, out-of-window or invalid-price anchors", () => {
    for (const anchor of [{ logical: 0.5, price: 12 }, { logical: 2, price: 12 }, { logical: 1, price: Number.NaN }])
      expect(() => serializeReviewDrawings([{ ...line, anchors: [anchor, line.anchors[1]] }], candles)).toThrow();
  });
  it("rejects duplicate IDs, incomplete drawings and non-monotonic candles", () => {
    expect(() => serializeReviewDrawings([line, line], candles)).toThrow();
    expect(() => serializeReviewDrawings([{ ...line, anchors: [line.anchors[0]] }], candles)).toThrow();
    expect(() => serializeReviewDrawings([line], [candles[1], candles[0]])).toThrow();
  });
  it("requires immutable snapshot provenance and corrected geometry", () => {
    expect(() => buildGeometryReviewDraft({ ...base, barsSha256: "", label: "CONFIRMED" })).toThrow();
    expect(() => buildGeometryReviewDraft({ ...base, drawings: [], label: "GEOMETRY_CORRECTED" })).toThrow();
    expect(buildGeometryReviewDraft({ ...base, label: "FALSE_POSITIVE" }).corrected_boundaries).toEqual([]);
  });
});

describe("Editor two-pair review evidence", () => {
  const original: DrawingObject = { ...line, id: "upper", locked: true };
  const editable: DrawingObject = {
    ...line, id: "editable:upper",
    anchors: [{ logical: 0, price: 11.5 }, { logical: 1, price: 13 }],
  };
  const review = {
    signalId: "signal-1", snapshotRevision: "rev-1", barsSha256: "b".repeat(64),
    label: "GEOMETRY_CORRECTED" as const,
    frozenCandles: candles, referenceDrawings: [original],
    editableDrawings: [editable],
  };

  it("serializes ONLY owner editable copies to source ray IDs and stable UTC times", () => {
    const result = buildEditorGeometryReview(review);
    expect(result.corrected_boundaries).toEqual([{
      id: "upper", type: "trend",
      anchors: [
        { bar_open_time_ms: Date.parse(candles[0].time), price: 11.5 },
        { bar_open_time_ms: Date.parse(candles[1].time), price: 13 },
      ],
    }]);
    expect(original.anchors[0].price).toBe(12);
  });

  it("rejects missing or extra lines, wrong topology and unchanged originals", () => {
    expect(() => buildEditorGeometryReview({ ...review, editableDrawings: [] })).toThrow();
    expect(() => buildEditorGeometryReview({ ...review, editableDrawings: [editable, editable] })).toThrow();
    expect(() => buildEditorGeometryReview({
      ...review, editableDrawings: [{ ...editable, type: "ray" }],
    })).toThrow();
    expect(() => buildEditorGeometryReview({
      ...review, editableDrawings: [{ ...editable, anchors: original.anchors }],
    })).toThrow(/No geometry changes/);
  });

  it("allows evidence labels without replacing the source geometry", () => {
    const result = buildEditorGeometryReview({
      ...review, label: "FALSE_POSITIVE", editableDrawings: [editable],
    });
    expect(result.corrected_boundaries).toEqual([]);
  });
});


describe("Editor ray deviation preview", () => {
  const sourceUpper: DrawingObject = { ...line, id: "upper", type: "ray", locked: true };
  const sourceLower: DrawingObject = {
    ...line, id: "lower", type: "ray", locked: true,
    anchors: [{ logical: 0, price: 9 }, { logical: 1, price: 10 }],
  };
  const changedUpper: DrawingObject = {
    ...sourceUpper, id: "editable:upper", locked: false,
    anchors: [{ logical: 0, price: 11.5 }, { logical: 1, price: 13 }],
  };
  const unchangedLower: DrawingObject = {
    ...sourceLower, id: "editable:lower", locked: false,
    anchors: sourceLower.anchors.map((anchor) => ({ ...anchor })),
  };
  const inputs = {
    referenceDrawings: [sourceUpper, sourceLower],
    editableDrawings: [changedUpper, unchangedLower],
    frozenCandles: candles,
  };
  it("compares both frozen rays in UTC and reports real price and slope deltas", () => {
    const deltas = compareEditorRayChanges(inputs);
    expect(deltas.map((item) => item.boundaryId)).toEqual(["upper", "lower"]);
    expect(deltas[0].anchorChanges[0].priceShiftPercent).toBeCloseTo(-4.1666666667);
    expect(deltas[0].anchorChanges[0].barShiftMs).toBe(0);
    expect(deltas[0].slopeDeltaPerHour).toBeCloseTo(6);
    expect(deltas[1].anchorChanges.every((item) => item.priceShift === 0)).toBe(true);
    expect(sourceUpper.anchors[0].price).toBe(12);
  });
  it("rejects fractional editor anchors or extra/foreign copied drawings", () => {
    expect(() => compareEditorRayChanges({
      ...inputs,
      editableDrawings: [{ ...changedUpper, anchors: [
        { logical: 0.25, price: 11.5 }, changedUpper.anchors[1],
      ] }, unchangedLower],
    })).toThrow(/frozen candle/);
    expect(() => compareEditorRayChanges({
      ...inputs, editableDrawings: [changedUpper, { ...unchangedLower, id: "editable:foreign" }],
    })).toThrow(/identity/);
    expect(() => compareEditorRayChanges({
      ...inputs, editableDrawings: [changedUpper, unchangedLower, unchangedLower],
    })).toThrow(/Incomplete/);
  });
});

describe("Stored geometry review receipt", () => {
  const ownerDraft = {
    ...buildGeometryReviewDraft({
      ...base, label: "GEOMETRY_CORRECTED", drawings: [
        { ...line, anchors: [{ logical: 0, price: 11.5 }, line.anchors[1]] },
      ],
    }),
    note: "Owner verified upper ray", idempotency_key: "owner-review-token-123456789",
  };
  const stored = {
    schema_version: ownerDraft.schema_version,
    signal_id: ownerDraft.signal_id,
    snapshot_revision: ownerDraft.snapshot_revision,
    bars_sha256: ownerDraft.bars_sha256,
    label: ownerDraft.label,
    idempotency_key: ownerDraft.idempotency_key,
    note: ownerDraft.note,
    corrected_boundaries: ownerDraft.corrected_boundaries.map((line) => ({
      boundary_id: line.id, kind: line.type,
      anchors: line.anchors.map((anchor) => ({ ...anchor })),
    })),
  };
  it("accepts exact saved UTC anchors in the store's canonical boundary format", () => {
    expect(matchesStoredGeometryReview(ownerDraft, stored)).toBe(true);
  });
  it("rejects substituted price/time, missing boundary, note or review label", () => {
    for (const corrupted of [
      { ...stored, corrected_boundaries: [{
        ...stored.corrected_boundaries[0], anchors: [
          { ...stored.corrected_boundaries[0].anchors[0], price: 999 },
          stored.corrected_boundaries[0].anchors[1],
        ],
      }] },
      { ...stored, corrected_boundaries: [{
        ...stored.corrected_boundaries[0], anchors: [
          { ...stored.corrected_boundaries[0].anchors[0], bar_open_time_ms: 1 },
          stored.corrected_boundaries[0].anchors[1],
        ],
      }] },
      { ...stored, corrected_boundaries: [] },
      { ...stored, note: "changed" },
      { ...stored, label: "FALSE_POSITIVE" },
    ]) expect(matchesStoredGeometryReview(ownerDraft, corrupted)).toBe(false);
  });
  it("rejects fabricated confirmations for a no-correction verdict", () => {
    const noCorrection = {
      ...ownerDraft, label: "CONFIRMED" as const, corrected_boundaries: [],
    };
    expect(matchesStoredGeometryReview(noCorrection, {
      ...stored, label: "CONFIRMED", corrected_boundaries: [],
    })).toBe(true);
    expect(matchesStoredGeometryReview(noCorrection, {
      ...stored, label: "CONFIRMED",
    })).toBe(false);
  });
});
