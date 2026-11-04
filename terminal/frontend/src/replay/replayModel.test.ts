import { describe, expect, it } from "vitest";
import { parseReplayDocument, syntheticReplay, visibleReplay } from "./replayModel";

describe("standalone SIMULATION viewer contract", () => {
  it("shows only completed candles and fills revealed at the current cursor", () => {
    const doc = syntheticReplay();
    expect(doc.source).toBe("SIMULATION");
    expect(doc.demo).toBe(true);
    const start = visibleReplay(doc.events, 0);
    expect(start.candles).toHaveLength(0);
    const signalIndex = doc.events.findIndex((e) => e.kind === "ENTRY_SIGNAL");
    expect(signalIndex).toBeGreaterThan(0);
    expect(visibleReplay(doc.events, signalIndex).signals).toHaveLength(0);
    expect(visibleReplay(doc.events, signalIndex + 1).signals).toHaveLength(1);
    expect(visibleReplay(doc.events, signalIndex + 1).fills).toHaveLength(0);
    const fillIndex = doc.events.findIndex((e) => e.kind === "ENTRY_FILLED");
    expect(visibleReplay(doc.events, fillIndex + 1).fills).toHaveLength(1);
    expect(visibleReplay(doc.events, fillIndex + 1).candles).toHaveLength(4);
    expect(visibleReplay(doc.events, fillIndex + 1).candles.at(-1)?.close).toBe(102);
    const ending = visibleReplay(doc.events, doc.events.length);
    expect(ending.candles).toHaveLength(16);
    expect(ending.exits).toHaveLength(1);
  });

  it("round trips emitted JSON string-number prices from the Python replay kernel", () => {
    const doc = syntheticReplay();
    const original = doc.events[0];
    if (!original.candle) throw new Error("fixture unexpectedly missing candle");
    const raw = JSON.parse(JSON.stringify(doc)) as {
      events: Array<{ candle?: Record<string, unknown> }>;
    };
    raw.events[0].candle!.open = "100.000";
    raw.events[0].candle!.low = "99";
    const parsed = parseReplayDocument(raw);
    expect(parsed.events[0].candle?.open).toBe(100);
    expect(parsed.events[0].candle?.low).toBe(99);
  });

  it("refuses PAPER and cross-account records instead of importing them", () => {
    const doc = syntheticReplay();
    expect(() => parseReplayDocument({ ...doc, source: "PAPER" })).toThrow(/SIMULATION/);
    expect(() => parseReplayDocument({
      ...doc,
      events: doc.events.map((e, index) => index === 0
        ? { ...e, source: "PAPER" } : e),
    })).toThrow(/другому источнику/);
    expect(() => parseReplayDocument({
      ...doc,
      events: doc.events.map((e, index) => index === 0
        ? { ...e, simulation_run_id: "OTHER" } : e),
    })).toThrow(/другому источнику/);
    expect(() => parseReplayDocument({
      ...doc,
      events: doc.events.map((e) => e.trade_id
        ? { ...e, trade_id: "PAPER-TRADE" } : e),
    })).toThrow(/чужого контура/);
  });

  it("rejects future OHLC in fill, broken sequence and reversed event time", () => {
    const doc = syntheticReplay();
    const fillIndex = doc.events.findIndex((e) => e.kind === "ENTRY_FILLED");
    const fill = doc.events[fillIndex];
    expect(() => parseReplayDocument({
      ...doc,
      events: doc.events.map((e, i) => i === fillIndex
        ? { ...e, candle: doc.events[0].candle } : e),
    })).toThrow(/Будущая OHLC/);
    expect(() => parseReplayDocument({
      ...doc,
      events: doc.events.map((e, i) => i === 1 ? { ...e, sequence: 42 } : e),
    })).toThrow(/последовательность/);
    expect(() => parseReplayDocument({
      ...doc,
      events: doc.events.map((e, i) => i === 1 ? { ...e, time_ms: 1 } : e),
    })).toThrow(/назад/);
    expect(fill.candle).toBeUndefined();
  });

  it("rejects overlapping or unfinished candle histories", () => {
    const doc = syntheticReplay();
    expect(() => parseReplayDocument({
      ...doc,
      events: doc.events.map((e, i) => i === 1
        ? { ...e, candle: { ...(e.candle ?? doc.events[0].candle), start_ms: doc.events[0].candle!.start_ms } }
        : e),
    })).toThrow();
    expect(() => parseReplayDocument({
      ...doc,
      events: doc.events.map((e, i) => i === 0
        ? { ...e, candle: { ...e.candle!, end_ms: e.time_ms + 300000 } } : e),
    })).toThrow(/закрытая свеча/);
  });
});
