import { describe, expect, it } from "vitest";
import { buildOwnerChartDraft, buildOwnerChartDraftV3, buildOwnerSignalDraft } from "./ownerSignalDraft";
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
      symbol: "BTCUSDT", timeframe: "5m", pattern: "Falling Wedge", direction: "LONG",
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
      symbol: "BTCUSDT", timeframe: "5m", pattern: "Falling Wedge" as const, direction: "SHORT" as const,
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

describe("Ikigai Box owner annotation", () => {
  const fib: DrawingObject = {
    ...ray("first-impulse", [20, 100], [30, 125]),
    type: "fibonacci",
  };

  it("freezes the upward first-impulse Fibonacci for SHORT, without fabricating two rays", () => {
    const draft = buildOwnerChartDraft({
      symbol: "BTCUSDT", timeframe: "5m", pattern: "Ikigai Box",
      direction: "SHORT", drawings: [fib], frozenCandles: candles,
      note: "First impulse, consolidation, second impulse",
      idempotencyKey: "ikigai-example-test-001",
    });
    expect(draft.schema_version).toBe(2);
    expect(draft.direction).toBe("SHORT");
    expect(draft.proposed_boundaries).toHaveLength(1);
    expect(draft.proposed_boundaries[0]).toEqual({
      id: "first_impulse_fibonacci", type: "fibonacci",
      anchors: [
        { bar_open_time_ms: Date.parse(candles[20].time), price: 100 },
        { bar_open_time_ms: Date.parse(candles[30].time), price: 125 },
      ],
    });
  });

  it("rejects an inverted direction or a generic rectangle in place of Fib", () => {
    const base = {
      symbol: "BTCUSDT", timeframe: "5m", pattern: "Ikigai Box" as const,
      direction: "LONG" as const, drawings: [fib],
      frozenCandles: candles, note: "", idempotencyKey: "ikigai-example-test-002",
    };
    expect(() => buildOwnerChartDraft(base)).toThrow(/Направление первого импульса/);
    expect(() => buildOwnerChartDraft({
      ...base, direction: "SHORT" as const,
      drawings: [{ ...fib, type: "rectangle" }],
    })).toThrow(/одну сетку Фибоначчи/);
  });
});

describe("untrusted V3 owner annotations", () => {
  const rays = [ray("hi", [30, 108], [80, 102]), ray("lo", [30, 95], [80, 92])];
  const base = {
    symbol: "BTCUSDT", timeframe: "5m",
    frozenCandles: candles, note: "", idempotencyKey: "owner-pattern-v3-000001",
  };

  it("stores formation movement independently of trade side", () => {
    const result = buildOwnerChartDraftV3({
      ...base, pattern: "Wedge", formationMovement: "UP",
      wedgeSubtype: "CORRECTION", drawings: rays,
    });
    expect(result.schema_version).toBe(3);
    expect(result.pattern).toBe("Wedge");
    expect(result.formation_movement).toBe("UP");
    expect(result.wedge_subtype).toBe("CORRECTION");
    expect(result).not.toHaveProperty("direction");
    expect(result).not.toHaveProperty("trade_side");
    expect(result.proposed_boundaries.map((x) => x.id)).toEqual(["manual_1", "manual_2"]);
  });

  it("stores the Box with its canonical pattern id and Fibonacci anchor", () => {
    const draft = buildOwnerChartDraftV3({
      ...base, pattern: "Ikigai Box", formationMovement: "UP",
      drawings: [{ ...rays[0], type: "fibonacci" }],
    });
    expect(draft.pattern).toBe("Ikigai Box");
    expect(draft.proposed_boundaries.map((x) => x.id)).toEqual(["first_impulse_fibonacci"]);
  });

  it("supports a G-shaped example without making a Robot candidate", () => {
    const draft = buildOwnerChartDraftV3({
      ...base, pattern: "G-Shaped", formationMovement: "DOWN",
      drawings: [{ ...rays[0], type: "horizontal", anchors: [rays[0].anchors[0]] }],
    });
    expect(draft.proposed_boundaries[0].type).toBe("horizontal");
    expect(draft).not.toHaveProperty("candidate_created");
  });

  it("saves two rays from a 200-candle source in a bounded contiguous 120-candle window", () => {
    const longCandles = Array.from({ length: 200 }, (_, i) => ({
      time: new Date(1792368000000 + i * 300000).toISOString(),
      open: 100, high: 110, low: 90, close: 100,
    }));
    const drawn = [
      ray("upper", [32, 108], [85, 102]),
      ray("lower", [35, 95], [82, 92]),
    ];
    const draft = buildOwnerChartDraftV3({
      ...base, frozenCandles: longCandles,
      pattern: "Wedge", formationMovement: "UP",
      wedgeSubtype: "CORRECTION", drawings: drawn,
    });
    expect(draft.bars).toHaveLength(120);
    expect(draft.bars.every((bar, index) =>
      index === 0 || bar.open_time_ms - draft.bars[index - 1].open_time_ms === 300000
    )).toBe(true);
    const times = new Set(draft.bars.map((bar) => bar.open_time_ms));
    expect(draft.proposed_boundaries.flatMap((line) => line.anchors)
      .every((point) => times.has(point.bar_open_time_ms))).toBe(true);
    expect(draft.proposed_boundaries[0].anchors[0].bar_open_time_ms)
      .toBe(Date.parse(longCandles[32].time));
    expect(draft.proposed_boundaries[1].anchors[1].bar_open_time_ms)
      .toBe(Date.parse(longCandles[82].time));
  });

  it("refuses a pattern spanning more than 120 bars rather than dropping an anchor", () => {
    const longCandles = Array.from({ length: 200 }, (_, i) => ({
      time: new Date(1792368000000 + i * 300000).toISOString(),
      open: 100, high: 110, low: 90, close: 100,
    }));
    expect(() => buildOwnerChartDraftV3({
      ...base, frozenCandles: longCandles,
      pattern: "Wedge", formationMovement: "UP",
      wedgeSubtype: "CORRECTION",
      drawings: [ray("upper", [15, 108], [150, 102]), ray("lower", [16, 95], [149, 92])],
    })).toThrow(/120 свечей/);
  });

  it("fails closed on missing wedge subtype and wrong geometry", () => {
    expect(() => buildOwnerChartDraftV3({
      ...base, pattern: "Wedge", formationMovement: "UP",
      drawings: rays,
    })).toThrow(/подтип/);
    expect(() => buildOwnerChartDraftV3({
      ...base, pattern: "Triangle", formationMovement: "DOWN",
      drawings: rays.slice(0, 1),
    })).toThrow(/два луча/);
  });
});
