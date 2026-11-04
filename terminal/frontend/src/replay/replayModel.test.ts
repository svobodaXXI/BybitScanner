import { describe, expect, it } from "vitest";
import { parseReplayDocument, syntheticReplay, visibleReplay, visibleGeometry } from "./replayModel";

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

  it("accepts real Bybit candle-only runs and refuses fake trade activity", () => {
    const base = syntheticReplay();
    const onlyBars = base.events.filter((event) => event.kind === "CANDLE_CLOSED")
      .map((event, i) => ({
        ...event,
        sequence: i + 1,
      }));
    const archive = {
      source: "SIMULATION" as const,
      simulation_run_id: base.simulation_run_id,
      mode: "MARKET_ONLY",
      market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT",
      timeframe: "5m",
      events: onlyBars,
    };
    const parsed = parseReplayDocument(archive);
    expect(parsed.mode).toBe("MARKET_ONLY");
    expect(parsed.symbol).toBe("BTCUSDT");
    expect(parsed.events).toHaveLength(16);
    expect(visibleReplay(parsed.events, parsed.events.length).fills).toHaveLength(0);
    expect(visibleReplay(parsed.events, parsed.events.length).candles).toHaveLength(16);
    expect(() => parseReplayDocument({
      ...archive,
      events: [...onlyBars, { ...base.events.find((e) => e.kind === "ENTRY_SIGNAL")!,
        sequence: onlyBars.length + 1, time_ms: onlyBars.at(-1)!.time_ms }],
    })).toThrow(/не должен содержать сделок/);
    expect(() => parseReplayDocument({ ...archive, demo: true })).toThrow(/идентичность/);
    expect(() => parseReplayDocument({ ...archive, source: "PAPER" })).toThrow(/SIMULATION/);
  });

  it("reveals provisional hourly lines and the blue slope only after their confirmation", () => {
    const example = syntheticReplay();
    const bars = example.events.filter((x) => x.kind === "CANDLE_CLOSED")
      .map((x, i) => ({ ...x, sequence: i + 1 }));
    const t0 = bars[0].candle!.start_ms;
    const mainAt = bars[7].time_ms;
    const refAt = bars[11].time_ms;
    const archive = {
      source: "SIMULATION",
      simulation_run_id: example.simulation_run_id,
      mode: "MARKET_ONLY",
      market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m",
      events: bars,
      geometry: [
        { kind: "MAIN_1H", side: "BULL", available_at_ms: mainAt,
          from_ms: t0, to_ms: bars[3].candle!.start_ms, from_price: "99",
          to_price: "101", trend_version: mainAt, classification: "UNVALIDATED_GEOMETRY_ONLY" },
        { kind: "TARGET_1H", side: "BULL", available_at_ms: mainAt,
          from_ms: bars[1].candle!.start_ms, to_ms: bars[4].candle!.start_ms,
          from_price: "107", to_price: "108",
          trend_version: mainAt, classification: "UNVALIDATED_GEOMETRY_ONLY" },
        { kind: "REFERENCE_5M", side: "BULL", available_at_ms: refAt,
          from_ms: bars[5].candle!.start_ms, to_ms: bars[9].candle!.start_ms,
          from_price: "106", to_price: "104",
          trend_version: mainAt, classification: "UNVALIDATED_GEOMETRY_ONLY" },
      ],
    };
    const doc = parseReplayDocument(archive);
    expect(visibleGeometry(doc, null)).toEqual([]);
    expect(visibleGeometry(doc, mainAt - 1)).toEqual([]);
    expect(visibleGeometry(doc, mainAt).map((x) => x.kind)).toEqual(["MAIN_1H", "TARGET_1H"]);
    expect(visibleGeometry(doc, refAt - 1).map((x) => x.kind)).toEqual(["MAIN_1H", "TARGET_1H"]);
    expect(visibleGeometry(doc, refAt).map((x) => x.kind)).toEqual([
      "MAIN_1H", "TARGET_1H", "REFERENCE_5M",
    ]);
    expect(() => parseReplayDocument({
      ...archive, geometry: [{ ...archive.geometry[0], available_at_ms: bars.at(-1)!.time_ms + 1 }],
    })).toThrow(/будущее/);
    expect(() => parseReplayDocument({
      ...archive, geometry: [{ ...archive.geometry[0], classification: "TRADE_APPROVED" }],
    })).toThrow(/торговый сигнал/);
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
