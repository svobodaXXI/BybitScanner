import { describe, expect, it } from "vitest";
import { buildOwnerChartDraft, buildOwnerSignalDraft } from "./ownerSignalDraft";
import type { DrawingObject } from "../chart/drawingModel";

const candles = Array.from({ length: 120 }, (_, i) => ({
  time: new Date(1792368000000 + i * 300000).toISOString(),
  open: 100, high: 110, low: 90, close: 100,
}));
const ray = (id: string, a: [number, number], b: [number, number]): DrawingObject => ({
  id, type: "ray", anchors: [
    { logical: a[0], price: a[1] }, { logical: b[0], price: b[1] },
  ],
  style: { color: "#e0b45b", lineWidth: 1.5 }, locked: false, hidden: false,
});
const input = {
  signalId: "source:BTCUSDT:5:abc", snapshotRevision: "a".repeat(64),
  barsSha256: "b".repeat(64), pattern: "Falling Wedge" as const,
  note: "", idempotencyKey: "owner-proposal-test-000001", frozenCandles: candles,
};

describe("owner new-signal draft", () => {
  it("preserves exact frozen timestamps and orders user rays by upper/lower", () => {
    const proposal = buildOwnerSignalDraft({
      ...input,
      drawings: [
        ray("manual-low", [30, 95], [80, 92]),
        ray("manual-high", [30, 108], [80, 102]),
      ],
    });
    expect(proposal.proposed_boundaries.map((line) => line.id)).toEqual(["upper", "lower"]);
    expect(proposal.proposed_boundaries[0].anchors[0].bar_open_time_ms)
      .toEqual(Date.parse(candles[30].time));
    expect(proposal.proposed_boundaries[1].anchors[1].price).toBe(92);
    expect(proposal.signal_id).toBe(input.signalId);
    expect(proposal.idempotency_key).toBe(input.idempotencyKey);
  });

  it("refuses incomplete, non-ray and out-of-range geometry", () => {
    const upper = ray("a", [30, 108], [80, 102]);
    const lower = ray("b", [30, 95], [80, 92]);
    expect(() => buildOwnerSignalDraft({ ...input, drawings: [upper] })).toThrow(/два луча/);
    expect(() => buildOwnerSignalDraft({
      ...input, drawings: [{ ...upper, type: "trend" }, lower],
    })).toThrow(/два луча/);
    expect(() => buildOwnerSignalDraft({
      ...input, drawings: [upper, { ...lower, anchors: [
        { logical: 30, price: 95 }, { logical: 300, price: 92 },
      ] }],
    })).toThrow(/frozen candle/);
    expect(() => buildOwnerSignalDraft({
      ...input, drawings: [upper, { ...lower, anchors: [
        { logical: 80, price: 92 }, { logical: 30, price: 95 },
      ] }],
    })).toThrow(/по времени/);
  });
});


describe("retrospective owner new-signal proposal", () => {
  it("carries review-as-of evidence without changing immutable signal identity", () => {
    const asOf = Date.parse(candles.at(-1)!.time);
    const result = buildOwnerSignalDraft({
      ...input,
      drawings: [ray("hi", [30, 108], [80, 102]), ray("lo", [30, 95], [80, 92])],
      contextAsOfMs: asOf, contextBarsSha256: "c".repeat(64),
    });
    expect(result.context_as_of_ms).toBe(asOf);
    expect(result.context_bars_sha256).toBe("c".repeat(64));
    expect(result.snapshot_revision).toBe(input.snapshotRevision);
  });
});


describe("independent owner signal on a current chart", () => {
  it("serializes closed candles and two manual rays without Scanner provenance", () => {
    const draft = buildOwnerChartDraft({
      symbol: "BTCUSDT", timeframe: "5m", pattern: "Falling Wedge",
      drawings: [ray("low", [30, 95], [80, 92]), ray("upper", [30, 108], [80, 102])],
      frozenCandles: candles, note: "Missed by Scanner",
      idempotencyKey: "owner-missed-00000001",
    });
    expect(draft.source_kind).toBe("OWNER_CHART_UNVERIFIED");
    expect(draft.timeframe).toBe("5");
    expect(draft.bars).toHaveLength(120);
    expect(draft.bars[30].open_time_ms).toBe(Date.parse(candles[30].time));
    expect(draft.proposed_boundaries.map((line) => line.id)).toEqual(["upper", "lower"]);
    expect(draft).not.toHaveProperty("signal_id");
    expect(draft).not.toHaveProperty("snapshot_revision");
  });

  it("refuses gaps and incomplete rays before sending owner data", () => {
    const base = {
      symbol: "BTCUSDT", timeframe: "5m", pattern: "Falling Wedge" as const,
      frozenCandles: candles, note: "", idempotencyKey: "owner-missed-00000002",
      drawings: [ray("upper", [30, 108], [80, 102]), ray("lower", [30, 95], [80, 92])],
    };
    expect(() => buildOwnerChartDraft({ ...base, drawings: base.drawings.slice(0, 1) }))
      .toThrow(/два луча/);
    expect(() => buildOwnerChartDraft({
      ...base, frozenCandles: [...candles.slice(0, 40), ...candles.slice(41)],
    })).toThrow(/Пропуск/);
  });
});
