import { describe, expect, it } from "vitest";
import { completeHourlyCandles, nextClosedCandleCursor, stepReplayCursor, parseReplayDocument, syntheticReplay, simulationActionJournal, visibleReplay, visibleGeometry, visibleGeometryHistory, visiblePriorLevels, visiblePriorBreaks, visibleDmi, visibleObservations, visibleH017BlueRiskPreviews, studyH017BlueCandidates, visibleH017CandidateStudy, type ReplayDocument } from "./replayModel";

describe("standalone SIMULATION viewer contract", () => {
  it("derives only completed hourly OHLCV from contiguous 5m Bybit candles", () => {
    const t = Date.UTC(2026, 10, 2);
    const bars = Array.from({ length: 13 }, (_, i) => ({
      start_ms: t + 300_000 * i, end_ms: t + 300_000 * (i + 1),
      open: 100 + i, close: 100.5 + i,
      high: 102 + i, low: 99 + i, volume: i + 1,
    }));
    expect(completeHourlyCandles(bars.slice(0, 11))).toEqual([]);
    expect(completeHourlyCandles(bars.slice(0, 12))).toEqual([{
      start_ms: t, end_ms: t + 3_600_000,
      open: 100, high: 113, low: 99, close: 111.5, volume: 78,
    }]);
    expect(completeHourlyCandles(bars)).toHaveLength(1); // Last H1 is incomplete.
    expect(completeHourlyCandles([bars[0], ...bars.slice(2, 12)])).toEqual([]); // A gap is not invented.
  });

  it("never paints H1 geometry from only three closed hourly pivots", () => {
    const hour = 3_600_000, m5 = 300_000;
    const start = Date.UTC(2026, 7, 20, 0);
    const highs = [115, 114, 113, 118, 122, 130, 125, 120, 116, 115, 114];
    const lows = [109, 106, 90, 101, 108, 112, 110, 105, 100, 107, 108];
    const context_1h = highs.map((high, index) => ({
      start_ms: start + index * hour, end_ms: start + (index + 1) * hour,
      open: (high + lows[index]) / 2, close: (high + lows[index]) / 2,
      high, low: lows[index], volume: 12,
    }));
    const start_ms = start + 11 * hour;
    const candle = {
      start_ms, end_ms: start_ms + m5, open: 112, high: 113,
      low: 111, close: 112, volume: 1,
    };
    const document: ReplayDocument = {
      source: "SIMULATION", simulation_run_id: "three_pivots_blocked", mode: "MARKET_ONLY",
      symbol: "GRASSUSDT", timeframe: "5m", context_1h,
      events: [{ source: "SIMULATION", simulation_run_id: "three_pivots_blocked",
        kind: "CANDLE_CLOSED", sequence: 1, time_ms: candle.end_ms, candle }],
      geometry: [], hourly_prior_breaks: [], hourly_prior_updates: [],
    };
    // Exactly one producer is authoritative: the archived publication log.
    expect(visibleGeometryHistory(document, candle.end_ms)).toEqual([]);
    expect(visibleGeometry(document, candle.end_ms)).toEqual([]);
    const laterMs = candle.end_ms + m5;
    const published: ReplayDocument = {
      ...document,
      geometry: [{
        kind: "MAIN_1H", side: "BULL", from_ms: start + 2 * hour,
        to_ms: start + 8 * hour, from_price: 90, to_price: 100,
        trend_version: laterMs, available_at_ms: laterMs,
        classification: "UNVALIDATED_GEOMETRY_ONLY",
      }],
    };
    // Frozen archive publication is a separate source of truth; the
    // visual-only three-pivot calculation cannot move it into the past.
    expect(visibleGeometry(published, candle.end_ms)).toEqual([]);
    expect(visibleGeometry(published, laterMs)).toHaveLength(1);
  });

  it("steps H1 by a completed hour and M5 by one candle including synchronous rows", () => {
    const start = Date.UTC(2026, 7, 20);
    const m5 = 300_000;
    const events = Array.from({ length: 25 }, (_, index) => {
      const time_ms = start + (index + 1) * m5;
      return {
        source: "SIMULATION" as const, simulation_run_id: "tf_step",
        sequence: index + 1, kind: "CANDLE_CLOSED" as const, time_ms,
        candle: {
          start_ms: time_ms - m5, end_ms: time_ms,
          open: 100, high: 101, low: 99, close: 100, volume: 1,
        },
      };
    });
    expect(stepReplayCursor(events, 0, "1h", 1)).toBe(12);
    expect(stepReplayCursor(events, 12, "1h", 1)).toBe(24);
    expect(stepReplayCursor(events, 24, "1h", -1)).toBe(12);
    expect(stepReplayCursor(events, 12, "1h", -1)).toBe(0);
    expect(stepReplayCursor(events, 0, "1h", -1)).toBe(0);
    expect(stepReplayCursor(events, 24, "5m", -1)).toBe(23);
    expect(stepReplayCursor(events, 12, "5m", 1)).toBe(13);
    expect(stepReplayCursor(events, 25, "1h", 1)).toBe(25); // 25th M5 is an incomplete H1.
  });

  it("validates dashed M5 acceleration provenance against four known swings", () => {
    const t = Date.UTC(2026, 9, 1), step = 300_000;
    const source_pivots = [
      { kind: "LOW", at_ms: t, confirmed_at_ms: t + 3 * step, price: 90 },
      { kind: "HIGH", at_ms: t + 2 * step, confirmed_at_ms: t + 5 * step, price: 95 },
      { kind: "LOW", at_ms: t + 4 * step, confirmed_at_ms: t + 7 * step, price: 91 },
      { kind: "HIGH", at_ms: t + 6 * step, confirmed_at_ms: t + 9 * step, price: 98 },
    ];
    const line = {
      kind: "ACCELERATION_5M", side: "BULL", from_ms: t, to_ms: t + 4 * step,
      from_price: 90, to_price: 91, available_at_ms: t + 16 * step,
      trend_version: t + 12 * step, source_pivots,
      classification: "UNVALIDATED_GEOMETRY_ONLY",
    };
    const candle = {
      start_ms: t + 19 * step, end_ms: t + 20 * step,
      open: 101, high: 102, low: 99, close: 100, volume: 1,
    };
    const doc = {
      source: "SIMULATION", mode: "MARKET_ONLY", simulation_run_id: "audit-4p",
      market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m",
      events: [{ source: "SIMULATION", simulation_run_id: "audit-4p",
        kind: "CANDLE_CLOSED", sequence: 1, time_ms: candle.end_ms, candle }],
      geometry: [line],
    };
    const parsed = parseReplayDocument(doc);
    expect(parsed.geometry?.[0].kind).toBe("ACCELERATION_5M");
    expect(parsed.geometry?.[0].source_pivots).toHaveLength(4);
    expect(visibleGeometryHistory(parsed, t + 15 * step)).toEqual([]);
    expect(visibleGeometryHistory(parsed, candle.end_ms)).toHaveLength(1);
    expect(() => parseReplayDocument({
      ...doc, geometry: [{ ...line, source_pivots: source_pivots.slice(0, 3) }],
    })).toThrow(/четыре/);
    expect(() => parseReplayDocument({
      ...doc, geometry: [{ ...line,
        source_pivots: source_pivots.map((p, i) => i === 3
          ? { ...p, confirmed_at_ms: line.available_at_ms + step } : p) }],
    })).toThrow(/Неподтверждённый/);
    expect(() => parseReplayDocument({
      ...doc, geometry: [{ ...line,
        source_pivots: source_pivots.map((p, i) => i === 3
          ? { ...p, price: 92 } : p) }],
    })).toThrow(/не подтверждают направление/);
  });

  it("retains distinct official trade-derived provenance for real archive replay", () => {
    const events = syntheticReplay().events.filter(e => e.kind === "CANDLE_CLOSED")
      .map((e, i) => ({ ...e, sequence: i + 1, simulation_run_id: "public_archive" }));
    const input = {
      source: "SIMULATION", simulation_run_id: "public_archive",
      mode: "MARKET_ONLY", symbol: "GRASSUSDT", timeframe: "5m", events,
      market_data_source: "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M",
      geometry: [], hourly_prior_updates: [], hourly_prior_breaks: [],
    };
    const accepted = parseReplayDocument(input);
    expect(accepted.market_data_source).toBe("BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M");
    expect(accepted.events).toHaveLength(events.length);
    expect(visiblePriorBreaks(accepted, events.at(-1)!.time_ms)).toEqual([]);
    expect(() => parseReplayDocument({
      ...input, market_data_source: "BYBIT_PRIVATE_HISTORY",
    })).toThrow();
  });

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
    expect(ending.candles).toHaveLength(64);
    expect(ending.exits).toHaveLength(1);
  });

  it("uses exactly one closed M5 per play/forward frame, even across trade journal rows", () => {
    const events = syntheticReplay().events;
    let cursor = 0;
    for (let candle = 1; candle <= 64; candle++) {
      const next = nextClosedCandleCursor(events, cursor);
      expect(next).toBeGreaterThan(cursor);
      const frame = visibleReplay(events, next);
      expect(frame.candles).toHaveLength(candle);
      expect(events.slice(0, next).every(event => event.time_ms <= frame.lastTimeMs!)).toBe(true);
      // At the fourth M5 close both its signal and the NEXT M5 open fill
      // are already timestamped exactly at that close: an atomic frame.
      if (candle === 3) {
        expect(frame.signals).toHaveLength(0);
        expect(frame.fills).toHaveLength(0);
      }
      if (candle === 4) {
        expect(frame.signals).toHaveLength(1);
        expect(frame.fills).toHaveLength(1);
      }
      if (candle === 9) expect(frame.exits).toHaveLength(1);
      cursor = next;
    }
    expect(cursor).toBe(events.length);
    expect(nextClosedCandleCursor(events, cursor)).toBe(cursor);
    expect(nextClosedCandleCursor(events, 0)).toBe(1);
  });

  it("exports only recorded virtual actions and never erases them on rewind", () => {
    const demo = syntheticReplay();
    const report = simulationActionJournal(demo);
    expect(report.source).toBe("SIMULATION");
    expect(report.report_kind).toBe("RECORDED_ACTIONS_ONLY");
    expect(report.actions.map(item => item.kind)).toEqual([
      "ENTRY_SIGNAL", "ENTRY_FILLED", "EXIT_FILLED",
    ]);
    expect(report.actions.map(item => item.event_id)).toEqual(
      report.actions.map(item => `${item.simulation_run_id}:${item.sequence}`),
    );
    expect(report.actions[0]).toMatchObject({ side: "LONG", comment: "Сигнал LONG" });
    expect(report.actions[1]).toMatchObject({ side: "LONG", comment: "Вход LONG" });
    expect(report.actions[2]).toMatchObject({ reason: "DEMO_EXIT", comment: "Выход DEMO_EXIT" });
    const original = JSON.stringify(report);
    const firstFill = demo.events.findIndex(item => item.kind === "ENTRY_FILLED");
    expect(visibleReplay(demo.events, firstFill).fills).toHaveLength(0);
    expect(visibleReplay(demo.events, demo.events.length).exits).toHaveLength(1);
    expect(JSON.stringify(simulationActionJournal(demo))).toBe(original);
    const marketOnly = parseReplayDocument({
      source: "SIMULATION", simulation_run_id: "history", mode: "MARKET_ONLY",
      market_data_source: "BYBIT_PUBLIC_KLINE", symbol: "BTCUSDT", timeframe: "5m",
      events: demo.events.filter(item => item.kind === "CANDLE_CLOSED").map((item, index) => ({
        ...item, simulation_run_id: "history", sequence: index + 1,
      })),
    });
    expect(simulationActionJournal(marketOnly).actions).toEqual([]);
  });

  it("warmed synthetic ADX is displayed only on completed 5m candles", () => {
    const doc = syntheticReplay();
    expect(doc.demo).toBe(true);
    expect(doc.mode).toBe("STRATEGY");
    expect(doc.dmi_5m?.points).toHaveLength(64);
    expect(doc.dmi_5m?.points[26].adx).toBeNull();
    expect(doc.dmi_5m?.points[27].adx).not.toBeNull();
    expect(visibleDmi(doc, 0)).toEqual([]);
    expect(visibleDmi(doc, 27).at(-1)?.adx).toBeNull();
    expect(visibleDmi(doc, 28).at(-1)?.adx).not.toBeNull();
    expect(visibleDmi(doc, 64).at(-1)?.plus_di).toBeGreaterThan(0);
  });

  it("verifies same-close DI/ADX/20 crossings and never reveals the next candle", () => {
    const demo = syntheticReplay();
    const raw = JSON.parse(JSON.stringify(demo));
    const points = raw.dmi_5m.points;
    const at = points[29].time_ms;
    points[28] = { ...points[28], plus_di: "19", minus_di: "21", adx: "18" };
    points[29] = {
      ...points[29], plus_di: "23", minus_di: "17", adx: "20",
      crossings: [
        { time_ms: at, side: "PLUS", direction: "UP", comparator: "OPPOSITE_DI" },
        { time_ms: at, side: "PLUS", direction: "UP", comparator: "LEVEL_20" },
        { time_ms: at, side: "MINUS", direction: "DOWN", comparator: "OPPOSITE_DI" },
        { time_ms: at, side: "MINUS", direction: "DOWN", comparator: "LEVEL_20" },
        { time_ms: at, side: "MINUS", direction: "DOWN", comparator: "ADX" },
      ],
    };
    const parsed = parseReplayDocument(raw);
    expect(visibleDmi(parsed, 29).flatMap(p => p.crossings ?? [])).toHaveLength(0);
    expect(visibleDmi(parsed, 30).flatMap(p => p.crossings ?? [])).toHaveLength(5);
    expect(visibleReplay(parsed.events, parsed.events.length).fills).toHaveLength(1); // Demo only.
    expect(() => parseReplayDocument({
      ...raw, dmi_5m: { ...raw.dmi_5m, points: points.map((p: { crossings?: Array<Record<string, unknown>> }, i: number) =>
        i === 29 ? { ...p, crossings: [{ ...p.crossings![0], time_ms: at + 300_000 }] } : p) },
    })).toThrow(/Пересечение ADX\/DMI/);
    expect(() => parseReplayDocument({
      ...raw, dmi_5m: { ...raw.dmi_5m, points: points.map((p: { crossings?: Array<Record<string, unknown>> }, i: number) =>
        i === 29 ? { ...p, crossings: [...p.crossings!].reverse() } : p) },
    })).toThrow(/Пересечение ADX\/DMI/);
    expect(() => parseReplayDocument({
      ...raw, dmi_5m: { ...raw.dmi_5m, points: points.map((p: { crossings?: Array<Record<string, unknown>> }, i: number) =>
        i === 29 ? { ...p, crossings: [{ ...p.crossings![0], direction: "DOWN" }] } : p) },
    })).toThrow(/Пересечение ADX\/DMI/);
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
    expect(parsed.events).toHaveLength(64);
    expect(visibleReplay(parsed.events, parsed.events.length).fills).toHaveLength(0);
    expect(visibleReplay(parsed.events, parsed.events.length).candles).toHaveLength(64);
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
    const doc = parseReplayDocument({ ...archive, geometry_warmup_hours: 72 });
    expect(doc.geometry_warmup_hours).toBe(72);
    expect(() => parseReplayDocument({ ...archive, geometry_warmup_hours: 73 }))
      .toThrow(/предыстория/);
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

  it("retires stale H1 target and M5 reference across successive main revisions", () => {
    const demo = syntheticReplay();
    const bars = demo.events.filter(event => event.kind === "CANDLE_CLOSED")
      .map((event, index) => ({
        ...event, sequence: index + 1, simulation_run_id: "multi_revision",
      }));
    const t = (index: number) => bars[index].candle!.start_ms;
    const known = (index: number) => bars[index].time_ms;
    const base = {
      side: "BULL", classification: "UNVALIDATED_GEOMETRY_ONLY",
      from_price: "10", to_price: "11",
    };
    const geometry = [
      { ...base, kind: "MAIN_1H", from_ms: t(0), to_ms: t(3),
        available_at_ms: known(8), trend_version: known(8) },
      { ...base, kind: "TARGET_1H", from_ms: t(1), to_ms: t(4),
        available_at_ms: known(8), trend_version: known(8) },
      { ...base, kind: "REFERENCE_5M", from_ms: t(5), to_ms: t(7),
        available_at_ms: known(11), trend_version: known(8) },
      { ...base, kind: "MAIN_1H", from_ms: t(0), to_ms: t(20),
        available_at_ms: known(27), trend_version: known(27) },
      { ...base, kind: "TARGET_1H", from_ms: t(1), to_ms: t(21),
        available_at_ms: known(29), trend_version: known(27) },
      { ...base, kind: "REFERENCE_5M", from_ms: t(25), to_ms: t(30),
        available_at_ms: known(35), trend_version: known(27) },
      { ...base, kind: "MAIN_1H", from_ms: t(0), to_ms: t(37),
        available_at_ms: known(44), trend_version: known(44) },
    ];
    const doc = parseReplayDocument({
      source: "SIMULATION", simulation_run_id: "multi_revision",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m", events: bars, geometry,
    });
    const before = visibleGeometry(doc, known(27) - 1);
    expect(before.map(item => item.kind)).toEqual([
      "MAIN_1H", "TARGET_1H", "REFERENCE_5M",
    ]);
    expect(visibleGeometry(doc, known(27)).map(item => item.kind)).toEqual(["MAIN_1H"]);
    expect(visibleGeometry(doc, known(29)).map(item => item.kind)).toEqual([
      "MAIN_1H", "TARGET_1H",
    ]);
    expect(visibleGeometry(doc, known(35)).map(item => item.kind)).toEqual([
      "MAIN_1H", "TARGET_1H", "REFERENCE_5M",
    ]);
    expect(visibleGeometry(doc, known(44)).map(item => item.kind)).toEqual(["MAIN_1H"]);
    const fullHistory = visibleGeometryHistory(doc, known(44));
    expect(fullHistory.map(item => item.superseded_at_ms)).toEqual([
      known(27), known(27), known(27), known(44), known(44), known(44),
      undefined,
    ]);
    // These are new versions of the same unbroken movement, not a reason to
    // truncate the prior solid slopes on the chart.
    expect(fullHistory.every(item => item.retired_at_ms === undefined)).toBe(true);
    expect(visibleGeometryHistory(doc, known(27) - 1)).toHaveLength(3);
    expect(visibleGeometryHistory(doc, known(27) - 1)
      .every(item => item.superseded_at_ms === undefined)).toBe(true);
    expect(visibleGeometryHistory(doc, known(35))[2].superseded_at_ms).toBe(known(27));
    expect(visibleGeometryHistory(doc, known(44)).map(item => item.from_ms)).toEqual(
      geometry.map(item => item.from_ms),
    );
  });

  it("replays purple priors only after a fully CLOSED H1 confirms the new extreme", () => {
    const demo = syntheticReplay();
    const events = demo.events.filter(e => e.kind === "CANDLE_CLOSED")
      .map((e, index) => ({ ...e, sequence: index + 1 }));
    const t0 = events[0].candle!.start_ms;
    const firstKnown = events[8].time_ms;
    const nextKnown = events[28].time_ms;
    const confirmedH1 = events[35].time_ms;
    const first = {
      kind: "MAIN_1H", side: "BEAR", available_at_ms: firstKnown,
      from_ms: t0, to_ms: events[3].candle!.start_ms,
      from_price: "120", to_price: "115", trend_version: firstKnown,
      classification: "UNVALIDATED_GEOMETRY_ONLY",
    };
    const next = {
      ...first, available_at_ms: nextKnown,
      // The first H1 wick belongs to this movement and never shifts.
      from_ms: t0, to_ms: events[22].candle!.start_ms,
      from_price: "120", to_price: "110", trend_version: nextKnown,
    };
    const archive = {
      source: "SIMULATION", simulation_run_id: "purple_fixture",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m",
      events: events.map(e => ({ ...e, simulation_run_id: "purple_fixture" })),
      geometry: [first, next],
    };
    // An H1 trendline revision/touch cannot move the prior on its own.
    const untouched = parseReplayDocument(archive);
    expect(visiblePriorLevels(untouched, nextKnown).map(p => p.price)).toEqual([115]);
    const withNewLow = archive.events.map((event, index) => index === 26
      ? { ...event, candle: { ...event.candle!, low: 50 } } : event);
    const doc = parseReplayDocument({ ...archive, events: withNewLow });
    expect(visiblePriorLevels(doc, null)).toEqual([]);
    expect(visiblePriorLevels(doc, firstKnown - 1)).toEqual([]);
    expect(visiblePriorLevels(doc, firstKnown).map(p => p.price)).toEqual([115]);
    // Low=50 appears on an already closed M5, but its H1 is still forming.
    expect(visiblePriorLevels(doc, nextKnown).map(p => p.price)).toEqual([115]);
    expect(visiblePriorLevels(doc, confirmedH1 - 300_000).map(p => p.price))
      .toEqual([115]);
    // No new geometry revision: the H1 CLOSE itself licenses the transfer.
    const after = visiblePriorLevels(doc, confirmedH1);
    expect(after.map(p => p.price)).toEqual([115, 110]);
    expect(after[0].superseded_at_ms).toBe(confirmedH1);
    expect(after[1].available_at_ms).toBe(confirmedH1);
    expect(after[1].superseded_at_ms).toBeUndefined();
    expect(after[1].at_ms).toBe(events[22].candle!.start_ms);
    expect(visiblePriorLevels(doc, confirmedH1 - 300_000)).toHaveLength(1);
    expect(visiblePriorLevels(demo, confirmedH1)).toEqual([]);
  });

  it("uses immutable Python purple-prior events and refuses invented H1 levels", () => {
    const sample = syntheticReplay();
    const events = sample.events.filter(e => e.kind === "CANDLE_CLOSED")
      .map((e, i) => ({ ...e, sequence: i + 1, simulation_run_id: "prior_kernel" }));
    const from = events[0].candle!.start_ms;
    const firstKnown = events[8].time_ms, nextKnown = events[28].time_ms;
    const geometry = [{
      kind: "MAIN_1H", side: "BEAR", available_at_ms: firstKnown,
      from_ms: from, to_ms: events[3].candle!.start_ms,
      from_price: "120", to_price: "115", trend_version: firstKnown,
      classification: "UNVALIDATED_GEOMETRY_ONLY",
    }, {
      kind: "MAIN_1H", side: "BEAR", available_at_ms: nextKnown,
      from_ms: from, to_ms: events[22].candle!.start_ms,
      from_price: "120", to_price: "110", trend_version: nextKnown,
      classification: "UNVALIDATED_GEOMETRY_ONLY",
    }];
    const first = { kind: "H1_PRIOR_CONFIRMED", side: "BEAR",
      at_ms: geometry[0].to_ms, price: "115", available_at_ms: firstKnown,
      trend_version: firstKnown, classification: "UNVALIDATED_GEOMETRY_ONLY" };
    const second = { ...first, at_ms: geometry[1].to_ms, price: "110",
      available_at_ms: nextKnown, trend_version: nextKnown };
    const input = {
      source: "SIMULATION", simulation_run_id: "prior_kernel",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m", events, geometry,
      hourly_prior_updates: [first, second],
    };
    const doc = parseReplayDocument(input);
    expect(visiblePriorLevels(doc, firstKnown - 1)).toEqual([]);
    expect(visiblePriorLevels(doc, nextKnown - 1).map(x => x.price)).toEqual([115]);
    expect(visiblePriorLevels(doc, nextKnown).map(x => x.price)).toEqual([115, 110]);
    expect(visiblePriorLevels(doc, nextKnown)[0].superseded_at_ms).toBe(nextKnown);
    expect(visiblePriorLevels(doc, nextKnown - 1).map(x => x.price)).toEqual([115]);
    expect(() => parseReplayDocument({ ...input, hourly_prior_updates: [
      first, { ...second, available_at_ms: nextKnown + 1 },
    ] })).toThrow();
    expect(() => parseReplayDocument({ ...input, hourly_prior_updates: [
      first, { ...second, price: "109" },
    ] })).toThrow();
  });

  it("handles bullish H1 prior moves symmetrically and ignores unfinished H1 highs", () => {
    const start = Date.UTC(2026, 10, 2);
    const step = 300_000;
    const bars = Array.from({ length: 48 }, (_, index) => ({
      source: "SIMULATION", simulation_run_id: "bull_prior",
      sequence: index + 1, kind: "CANDLE_CLOSED", time_ms: start + (index + 1) * step,
      candle: {
        start_ms: start + index * step, end_ms: start + (index + 1) * step,
        open: 100, close: 100, high: index === 39 ? 125 : 110,
        low: 90, volume: 1,
      },
    }));
    const firstKnown = bars[23].time_ms, secondKnown = bars[36].time_ms;
    const geometry = [{
      kind: "MAIN_1H", side: "BULL", available_at_ms: firstKnown,
      from_ms: start, to_ms: start + 12 * step,
      from_price: "80", to_price: "85", trend_version: firstKnown,
      classification: "UNVALIDATED_GEOMETRY_ONLY",
    }, {
      kind: "MAIN_1H", side: "BULL", available_at_ms: secondKnown,
      from_ms: start, to_ms: start + 24 * step,
      from_price: "80", to_price: "95", trend_version: secondKnown,
      classification: "UNVALIDATED_GEOMETRY_ONLY",
    }];
    const doc = parseReplayDocument({
      source: "SIMULATION", simulation_run_id: "bull_prior",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m", events: bars, geometry,
    });
    expect(visiblePriorLevels(doc, bars[39].time_ms).map(p => p.price)).toEqual([85]);
    expect(visiblePriorLevels(doc, bars[47].time_ms).map(p => p.price))
      .toEqual([85, 95]);
    expect(visiblePriorLevels(doc, bars[47].time_ms).at(-1)?.available_at_ms)
      .toBe(bars[47].time_ms);
    expect(visiblePriorLevels(doc, bars[46].time_ms).map(p => p.price))
      .toEqual([85]);
  });

  it("uses CLOSED warmup H1 wicks to move a purple prior when the first anchor predates the replay", () => {
    const hour = 3_600_000, step = 300_000;
    const base = Date.UTC(2026, 10, 2);
    const t = (h: number) => base + h * hour;
    const context_1h = [
      { start_ms: t(0), end_ms: t(1), open: 100, high: 125,
        low: 92, close: 100, volume: 12 },
      { start_ms: t(1), end_ms: t(2), open: 100, high: 120,
        low: 90, close: 100, volume: 12 },
    ];
    const events = Array.from({ length: 24 }, (_, i) => {
      const start_ms = t(2) + i * step;
      return {
        source: "SIMULATION", simulation_run_id: "h1_warmup",
        sequence: i + 1, kind: "CANDLE_CLOSED", time_ms: start_ms + step,
        candle: { start_ms, end_ms: start_ms + step,
          open: 100, high: 105, low: i === 15 ? 80 : 95,
          close: 100, volume: 1 },
      };
    });
    const firstKnown = events[0].time_ms;
    const secondKnown = events[11].time_ms;
    const geometry = [
      { kind: "MAIN_1H", side: "BEAR", available_at_ms: firstKnown,
        from_ms: t(0), to_ms: t(1), from_price: "120",
        to_price: "115", trend_version: firstKnown,
        classification: "UNVALIDATED_GEOMETRY_ONLY" },
      { kind: "MAIN_1H", side: "BEAR", available_at_ms: secondKnown,
        from_ms: t(0), to_ms: t(2), from_price: "120",
        to_price: "110", trend_version: secondKnown,
        classification: "UNVALIDATED_GEOMETRY_ONLY" },
    ];
    const input = {
      source: "SIMULATION", simulation_run_id: "h1_warmup",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m", events, geometry,
      geometry_warmup_hours: 2, context_1h,
    };
    const doc = parseReplayDocument(input);
    expect(doc.context_1h).toHaveLength(2);
    expect(visibleReplay(doc.events, doc.events.length).candles).toHaveLength(24);
    expect(visiblePriorLevels(doc, secondKnown).map(prior => prior.price)).toEqual([115]);
    expect(visiblePriorLevels(doc, events[22].time_ms).map(prior => prior.price))
      .toEqual([115]); // The new lower LOW belongs to an unfinished hour.
    const moved = visiblePriorLevels(doc, events[23].time_ms);
    expect(moved.map(prior => prior.price)).toEqual([115, 110]);
    expect(moved[1].available_at_ms).toBe(t(4));
    expect(visiblePriorLevels(doc, events[22].time_ms).map(prior => prior.price))
      .toEqual([115]); // Deterministic rewind.
    const legacy = parseReplayDocument({ ...input, context_1h: undefined });
    expect(visiblePriorLevels(legacy, events[23].time_ms).map(prior => prior.price))
      .toEqual([115]); // Missing archival proof must not fake the shift.
    expect(() => parseReplayDocument({
      ...input, context_1h: [{ ...context_1h[0], end_ms: t(3) }, context_1h[1]],
    })).toThrow(); // Impossible H1 duration.
    expect(() => parseReplayDocument({
      ...input, context_1h: [context_1h[0], { ...context_1h[1], end_ms: t(3) }],
    })).toThrow(); // Prehistory overlaps the first visible M5.
  });

  it("confirms a prior break only after a full H1 close and next H1 open beyond the level", () => {
    const hourMs = 3_600_000, step = 300_000;
    const start = Date.UTC(2026, 9, 1);
    const make = (side: "BULL" | "BEAR", finalClose: number, nextOpen: number) => {
      const bars = Array.from({ length: 36 }, (_, i) => {
        const open = i === 24 ? nextOpen : side === "BULL" ? 105 : 95;
        const close = i === 23 ? finalClose : i === 24 ? nextOpen : open;
        return {
          source: "SIMULATION", simulation_run_id: "prior_reversal",
          sequence: i + 1, kind: "CANDLE_CLOSED",
          time_ms: start + (i + 1) * step,
          candle: {
            start_ms: start + i * step, end_ms: start + (i + 1) * step,
            open, close, high: Math.max(open, close) + 1,
            low: Math.min(open, close) - 1, volume: 100,
          },
        };
      });
      const prior = side === "BULL" ? 100 : 100;
      return parseReplayDocument({
        source: "SIMULATION", simulation_run_id: "prior_reversal",
        mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
        symbol: "BTCUSDT", timeframe: "5m", events: bars,
        geometry: [{
          kind: "MAIN_1H", side, available_at_ms: start + hourMs,
          from_ms: start, to_ms: start + 5 * step,
          from_price: side === "BULL" ? "98" : "102", to_price: String(prior),
          trend_version: start + hourMs, classification: "UNVALIDATED_GEOMETRY_ONLY",
        }],
      });
    };
    for (const [side, finalClose, nextOpen, expected] of [
      ["BULL", 99, 98, "BEAR"],
      ["BEAR", 101, 102, "BULL"],
    ] as const) {
      const doc = make(side, finalClose, nextOpen);
      const knownAt = start + 2 * hourMs + step;
      expect(visiblePriorBreaks(doc, knownAt - 1)).toEqual([]);
      expect(visiblePriorBreaks(doc, knownAt - step)).toEqual([]);
      const breaks = visiblePriorBreaks(doc, knownAt);
      expect(breaks).toHaveLength(1);
      expect(breaks[0]).toMatchObject({
        kind: "PRIOR_CLOSE_NEXT_OPEN", previous_side: side, new_side: expected,
        confirmed_at_ms: knownAt, prior_price: 100,
        hourly_close_ms: start + 2 * hourMs,
      });
      expect(visiblePriorBreaks(doc, knownAt + hourMs)).toEqual(breaks); // no duplicates
      // The kernel owns the authoritative break; without its event the
      // market-only archive may NOT infer a reversal from prices alone.
      const priorLine = doc.geometry![0];
      const kernelPrior = {
        kind: "H1_PRIOR_CONFIRMED", side,
        at_ms: priorLine.to_ms, price: String(priorLine.to_price),
        available_at_ms: priorLine.available_at_ms,
        trend_version: priorLine.trend_version,
        classification: "UNVALIDATED_GEOMETRY_ONLY",
      };
      const canonicalInput = {
        ...doc, market_data_source: "BYBIT_PUBLIC_KLINE",
        hourly_prior_updates: [kernelPrior],
        hourly_prior_breaks: [breaks[0]],
      };
      const canonical = parseReplayDocument(canonicalInput);
      expect(visiblePriorBreaks(canonical, knownAt - step)).toEqual([]);
      expect(visiblePriorBreaks(canonical, knownAt)).toEqual(breaks);
      expect(visibleGeometry(canonical, knownAt)).toEqual([]);
      const noKernelBreak = parseReplayDocument({
        ...canonicalInput, hourly_prior_breaks: [],
      });
      expect(visiblePriorBreaks(noKernelBreak, knownAt)).toEqual([]);
      expect(visibleGeometry(noKernelBreak, knownAt)).toHaveLength(1);
      expect(() => parseReplayDocument({
        ...canonicalInput, hourly_prior_breaks: [{
          ...breaks[0], prior_price: 101,
        }],
      })).toThrow();
      expect(() => parseReplayDocument({
        ...canonicalInput, hourly_prior_breaks: [{
          ...breaks[0], confirmed_at_ms: knownAt - step,
        }],
      })).toThrow();
      expect(() => parseReplayDocument({
        ...canonicalInput, hourly_prior_breaks: [{
          ...breaks[0], next_hour_open_ms: knownAt,
        }],
      })).toThrow();
      expect(visiblePriorBreaks(doc, knownAt - step)).toEqual([]); // rewind
      expect(visibleGeometry(doc, knownAt - step)).toHaveLength(1);
      expect(visibleGeometry(doc, knownAt)).toEqual([]); // retired, no fake opposite
      expect(visibleGeometryHistory(doc, knownAt - step)).toHaveLength(1);
      expect(visibleGeometryHistory(doc, knownAt)).toMatchObject([
        { kind: "MAIN_1H", side, superseded_at_ms: knownAt },
      ]);
      expect(visibleGeometry(doc, knownAt - step)).toHaveLength(1); // restore old state
      // Full immutable archive and a genuinely truncated replay prefix must
      // produce identical break evidence at EVERY closed M5 playhead.
      for (let count = 12; count <= doc.events.length; count++) {
        const prefixEvents = doc.events.slice(0, count);
        const at = prefixEvents.at(-1)!.time_ms;
        const prefix = parseReplayDocument({
          source: "SIMULATION", simulation_run_id: doc.simulation_run_id,
          mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
          symbol: doc.symbol, timeframe: "5m", events: prefixEvents,
          geometry: doc.geometry!.filter(line => line.available_at_ms <= at),
        });
        expect(visiblePriorBreaks(doc, at)).toEqual(visiblePriorBreaks(prefix, at));
      }
    }
    expect(visiblePriorBreaks(make("BULL", 100.5, 99), start + 3 * hourMs)).toEqual([]);
    expect(visiblePriorBreaks(make("BULL", 99, 100.5), start + 3 * hourMs)).toEqual([]);
    expect(visiblePriorBreaks(make("BEAR", 99.5, 102), start + 3 * hourMs)).toEqual([]);
    expect(visiblePriorBreaks(make("BEAR", 101, 99.5), start + 3 * hourMs)).toEqual([]);
  });

  it("breaks the purple level frozen BEFORE the H1 candle, not its newly shifted version", () => {
    const start = Date.UTC(2026, 10, 3), hour = 3_600_000, step = 300_000;
    const events = Array.from({ length: 37 }, (_, index) => {
      const at = start + index * step;
      const open = index === 36 ? 98 : 105;
      const close = index === 35 ? 99 : open;
      return {
        source: "SIMULATION", simulation_run_id: "prior_frozen",
        sequence: index + 1, kind: "CANDLE_CLOSED", time_ms: at + step,
        candle: { start_ms: at, end_ms: at + step, open, close,
          high: index >= 24 && index <= 35 ? 150 : 112,
          low: Math.min(open, close) - 4, volume: 1 },
      };
    });
    const early = start + hour;
    const late = start + 3 * hour;
    const doc = parseReplayDocument({
      source: "SIMULATION", simulation_run_id: "prior_frozen",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m", events,
      geometry: [{
        kind: "MAIN_1H", side: "BULL", available_at_ms: early,
        from_ms: start, to_ms: start + step, from_price: "90",
        to_price: "100", trend_version: early,
        classification: "UNVALIDATED_GEOMETRY_ONLY",
      }, {
        kind: "MAIN_1H", side: "BULL", available_at_ms: late,
        from_ms: start, to_ms: start + hour, from_price: "90",
        to_price: "110", trend_version: late,
        classification: "UNVALIDATED_GEOMETRY_ONLY",
      }],
    });
    expect(visiblePriorLevels(doc, late).map(level => level.price)).toEqual([100, 110]);
    const confirmed = late + step;
    expect(visiblePriorBreaks(doc, confirmed - step)).toEqual([]);
    expect(visiblePriorBreaks(doc, confirmed)).toMatchObject([{
      kind: "PRIOR_CLOSE_NEXT_OPEN",
      previous_side: "BULL", new_side: "BEAR",
      confirmed_at_ms: confirmed, prior_price: 100,
      hourly_close_ms: late,
    }]);
    expect(visibleGeometry(doc, confirmed)).toEqual([]);
    expect(visiblePriorBreaks(doc, confirmed - step)).toEqual([]); // rewind
  });

  it("retires the blue M5 only at a known next OPEN crossing and restores it on rewind", () => {
    const demo = syntheticReplay();
    const events = demo.events.filter(e => e.kind === "CANDLE_CLOSED")
      .map((e, i) => ({ ...e, simulation_run_id: "blue_break", sequence: i + 1 }));
    const t = (i: number) => events[i].candle!.start_ms;
    const known = events[8].time_ms;
    const atBreak = events[11].time_ms;
    const geometry = [
      { kind: "MAIN_1H", side: "BULL", from_ms: t(0), to_ms: t(3),
        from_price: "90", to_price: "90", available_at_ms: known,
        trend_version: known, classification: "UNVALIDATED_GEOMETRY_ONLY" },
      { kind: "TARGET_1H", side: "BULL", from_ms: t(1), to_ms: t(4),
        from_price: "120", to_price: "120", available_at_ms: known,
        trend_version: known, classification: "UNVALIDATED_GEOMETRY_ONLY" },
      { kind: "REFERENCE_5M", side: "BULL", from_ms: t(0), to_ms: t(3),
        from_price: "105", to_price: "104", available_at_ms: known,
        trend_version: known, classification: "UNVALIDATED_GEOMETRY_ONLY" },
    ];
    const retirement = {
      kind: "REFERENCE_5M_OPEN_BREAK", time_ms: atBreak,
      open_ms: t(11), blue_available_at_ms: known, trend_version: known,
    };
    const archive = {
      source: "SIMULATION", simulation_run_id: "blue_break",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m", events, geometry,
      reference_5m_retirements: [retirement],
    };
    const doc = parseReplayDocument(archive);
    expect(visibleGeometry(doc, atBreak - 1).map(l => l.kind))
      .toEqual(["MAIN_1H", "TARGET_1H", "REFERENCE_5M"]);
    expect(visibleGeometry(doc, atBreak).map(l => l.kind))
      .toEqual(["MAIN_1H", "TARGET_1H"]);
    expect(visibleGeometryHistory(doc, atBreak).at(-1)?.superseded_at_ms)
      .toBe(atBreak);
    expect(visibleGeometryHistory(doc, atBreak - 1).at(-1)?.superseded_at_ms)
      .toBeUndefined();
    expect(visibleGeometry(doc, atBreak - 1)).toHaveLength(3);
    // Refining a correction must not retire its earlier solid slope. Both
    // immutable versions end only when the CURRENT correction truly breaks.
    const revisedBlue = {
      ...geometry[2], available_at_ms: events[9].time_ms,
      to_ms: t(4), to_price: "103",
    };
    const revised = parseReplayDocument({
      ...archive, geometry: [...geometry, revisedBlue],
      reference_5m_retirements: [{
        ...retirement, blue_available_at_ms: revisedBlue.available_at_ms,
      }],
    });
    const stillOpen = visibleGeometryHistory(revised, events[10].time_ms)
      .filter(item => item.kind === "REFERENCE_5M");
    expect(stillOpen).toHaveLength(2);
    expect(stillOpen.map(item => item.retired_at_ms)).toEqual([undefined, undefined]);
    expect(stillOpen[0].superseded_at_ms).toBe(revisedBlue.available_at_ms);
    const closed = visibleGeometryHistory(revised, atBreak)
      .filter(item => item.kind === "REFERENCE_5M");
    expect(closed.map(item => item.retired_at_ms)).toEqual([atBreak, atBreak]);
    expect(visibleGeometry(revised, atBreak).map(item => item.kind))
      .toEqual(["MAIN_1H", "TARGET_1H"]);
    expect(() => parseReplayDocument({
      ...archive, reference_5m_retirements: [{ ...retirement, open_ms: t(0) }],
    })).toThrow();
    expect(() => parseReplayDocument({
      ...archive, reference_5m_retirements: [{ ...retirement, time_ms: atBreak + 300_000 }],
    })).toThrow();
    expect(() => parseReplayDocument({
      ...archive, reference_5m_retirements: [{ ...retirement, kind: "UNVERIFIED_BREAK" }],
    })).toThrow();
  });

  it("reveals only completed H1 touch/reaction observations, never simulated fills", () => {
    const demo = syntheticReplay();
    const events = demo.events.filter(e => e.kind === "CANDLE_CLOSED")
      .map((event, i) => ({ ...event, sequence: i + 1 }));
    const first = events[11].time_ms;
    const second = events[12].time_ms;
    const version = events[5].time_ms;
    const archive = {
      source: "SIMULATION", simulation_run_id: "observation_fixture",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m", events: events.map(e => ({
        ...e, simulation_run_id: "observation_fixture",
      })),
      geometry: [{
        kind: "MAIN_1H", side: "BULL", available_at_ms: version,
        from_ms: events[0].candle!.start_ms,
        to_ms: events[1].candle!.start_ms,
        from_price: "100", to_price: "100", trend_version: version,
        classification: "UNVALIDATED_GEOMETRY_ONLY",
      }],
      observations: [
        { kind: "MAIN_1H_TOUCH", side: "BULL", time_ms: first,
          price: "101", line_price: "100", trend_version: version,
          classification: "UNVALIDATED_GEOMETRY_ONLY" },
        { kind: "MAIN_1H_REACTION", side: "BULL", time_ms: second,
          touch_time_ms: first, price: "103", line_price: "100",
          trend_version: version, classification: "UNVALIDATED_GEOMETRY_ONLY" },
      ],
    };
    const doc = parseReplayDocument(archive);
    expect(visibleObservations(doc, first - 1)).toHaveLength(0);
    expect(visibleObservations(doc, first).map(e => e.kind)).toEqual(["MAIN_1H_TOUCH"]);
    expect(visibleObservations(doc, second).map(e => e.kind)).toEqual([
      "MAIN_1H_TOUCH", "MAIN_1H_REACTION",
    ]);
    expect(visibleReplay(doc.events, doc.events.length).fills).toHaveLength(0);
    expect(() => parseReplayDocument({
      ...archive, geometry: undefined,
    })).toThrow(/Наблюдение не связано/);
    expect(() => parseReplayDocument({
      ...archive, observations: [{ ...archive.observations[0], trend_version: version + 300_000 }],
    })).toThrow(/Наблюдение не связано/);
    expect(() => parseReplayDocument({
      ...archive, observations: [{ ...archive.observations[0], side: "BEAR" }],
    })).toThrow(/Наблюдение не связано/);
    expect(() => parseReplayDocument({
      ...archive, observations: [{ ...archive.observations[0], price: "999" }],
    })).toThrow(/закрытой свечой/);
    expect(() => parseReplayDocument({
      ...archive, observations: [{ ...archive.observations[0], line_price: "101" }],
    })).toThrow(/трендовой/);
    expect(() => parseReplayDocument({
      ...archive, observations: [archive.observations[1]],
    })).toThrow(/без предыдущего/);
    expect(() => parseReplayDocument({
      ...archive, observations: [{ ...archive.observations[0], time_ms: second + 300_000 * 100 }],
    })).toThrow(/будущее/);
    expect(() => parseReplayDocument({
      ...archive, observations: [{ ...archive.observations[0], classification: "TRADE_APPROVED" }],
    })).toThrow(/Недостоверное/);
    expect(() => parseReplayDocument({
      ...archive, observations: [{ ...archive.observations[0], trend_version: second + 1 }],
    })).toThrow(/будущее/);
  });

  it("time-gates H-017 blue OPEN risk previews with actual candle and frozen line identity", () => {
    const demo = syntheticReplay();
    const events = demo.events.filter(e => e.kind === "CANDLE_CLOSED")
      .map((e, i) => ({ ...e, sequence: i + 1, simulation_run_id: "blue_risk_test" }));
    const ts = events[0].candle!.start_ms;
    const known = events[5].time_ms;
    const blueAt = events[6].time_ms;
    const start = events[10].candle!.start_ms;
    const startPrice = events[10].candle!.open;
    const rejectedAt = events[36].candle!.start_ms;
    const rejectedPrice = events[36].candle!.open;
    const geometry = [
      { kind: "MAIN_1H", side: "BULL", available_at_ms: known, trend_version: known,
        from_ms: ts, to_ms: ts + 300_000, from_price: "95", to_price: "95",
        classification: "UNVALIDATED_GEOMETRY_ONLY" },
      { kind: "TARGET_1H", side: "BULL", available_at_ms: known, trend_version: known,
        from_ms: ts, to_ms: ts + 300_000, from_price: "110", to_price: "110",
        classification: "UNVALIDATED_GEOMETRY_ONLY" },
      { kind: "REFERENCE_5M", side: "BULL", available_at_ms: blueAt, trend_version: known,
        from_ms: ts, to_ms: ts + 300_000, from_price: "100", to_price: "100",
        classification: "UNVALIDATED_GEOMETRY_ONLY" },
    ];
    const initial = {
      source: "SIMULATION", simulation_run_id: "blue_risk_test",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m", events, geometry,
      h017_blue_risk_previews: [
        { source: "SIMULATION", kind: "BLUE_5M_OPEN",
          classification: "UNVALIDATED_GEOMETRY_ONLY",
          time_ms: events[10].time_ms, open_ms: start,
          blue_available_at_ms: blueAt, trend_version: known, side: "LONG",
          entry_price: String(startPrice), blue_price: "100", target_price: "110",
          risk_status: "RISK_PASS",
          stop_price: String(startPrice * 0.993), quantity: String(10/startPrice) },
        { source: "SIMULATION", kind: "BLUE_5M_OPEN",
          classification: "UNVALIDATED_GEOMETRY_ONLY",
          time_ms: events[36].time_ms, open_ms: rejectedAt,
          blue_available_at_ms: blueAt, trend_version: known, side: "LONG",
          entry_price: String(rejectedPrice), blue_price: "100", target_price: "110",
          risk_status: "RISK_BELOW_1R" },
      ],
    };
    const doc = parseReplayDocument(initial);
    expect(visibleH017BlueRiskPreviews(doc, null)).toHaveLength(0);
    expect(visibleH017BlueRiskPreviews(doc, events[10].time_ms - 1)).toHaveLength(0);
    expect(visibleH017BlueRiskPreviews(doc, events[10].time_ms)).toHaveLength(1);
    expect(visibleH017BlueRiskPreviews(doc, events[36].time_ms)
      .map(x => x.risk_status)).toEqual(["RISK_PASS", "RISK_BELOW_1R"]);
    expect(visibleReplay(doc.events, doc.events.length).fills).toHaveLength(0);
    const altered = (i: number, x: Record<string, unknown>) => ({
      ...initial, h017_blue_risk_previews: initial.h017_blue_risk_previews.map(
        (r, n) => n === i ? { ...r, ...x } : r,
      ),
    });
    expect(() => parseReplayDocument({ ...initial, geometry: [] }))
      .toThrow(/геометрии/);
    expect(() => parseReplayDocument(altered(0, { entry_price: "1000" })))
      .toThrow(/свеча/);
    expect(() => parseReplayDocument(altered(0, { risk_status: "TRADE_APPROVED" })))
      .toThrow(/Недостоверный/);
    expect(() => parseReplayDocument(altered(0, { time_ms: events[15].time_ms })))
      .toThrow(/свеча/);
    expect(() => parseReplayDocument(altered(0, { stop_price: "1" })))
      .toThrow(/0,7%/);
    expect(() => parseReplayDocument(altered(0, { target_price: "100" })))
      .toThrow(/геометрии/);
    expect(() => parseReplayDocument(altered(1, { risk_status: "RISK_PASS",
      stop_price: String(rejectedPrice * 0.993), quantity: String(10/rejectedPrice) })))
      .toThrow(/1:1/);
  });

  it("compares frozen target/stop first touches against DMI known BEFORE candidate opening", () => {
    const start = Date.UTC(2026, 9, 2);
    const M5 = 300_000;
    const ohlc = [
      [100, 101, 99.5, 100],   // Preceding closed bar (DMI cross at close).
      [100, 101, 99.5, 100],   // Candidate 1: neither first touch.
      [100, 106, 99.5, 101],   // Candidate 1: frozen target first.
      [100, 106, 98, 101],     // Candidate 2: both touched in one bar.
      [100, 101, 98, 99],      // Candidate 3: stop first.
      [100, 101, 99.5, 100],   // Candidate 4: unresolved at end.
    ];
    const events = ohlc.map(([open, high, low, close], i) => ({
      source: "SIMULATION" as const, simulation_run_id: "study", sequence: i + 1,
      kind: "CANDLE_CLOSED" as const, time_ms: start + (i + 1) * M5,
      candle: { start_ms: start + i * M5, end_ms: start + (i + 1) * M5,
        open, high, low, close, volume: 10 },
    }));
    const candidate = (index: number, side: "LONG" | "SHORT" = "LONG") => ({
      source: "SIMULATION" as const, kind: "BLUE_5M_OPEN" as const,
      classification: "UNVALIDATED_GEOMETRY_ONLY" as const,
      time_ms: events[index].time_ms, open_ms: events[index].candle.start_ms,
      blue_available_at_ms: start, trend_version: start, side,
      entry_price: 100, blue_price: 99, target_price: side === "LONG" ? 105 : 95,
      risk_status: "RISK_PASS" as const, stop_price: side === "LONG" ? 99.3 : 100.7,
      quantity: 0.1,
    });
    const signal = { time_ms: events[0].time_ms, side: "PLUS" as const,
      direction: "UP" as const, comparator: "LEVEL_20" as const };
    const base: ReplayDocument = {
      source: "SIMULATION", simulation_run_id: "study", mode: "MARKET_ONLY",
      events, h017_blue_risk_previews: [1, 3, 4, 5].map(i => candidate(i)),
      dmi_5m: { source: "SIMULATION", timeframe: "5m", di_length: 14,
        adx_smoothing: 14, points: events.map((bar, i) => ({
          time_ms: bar.time_ms, plus_di: 24, minus_di: 12, adx: 21,
          crossings: i === 0 ? [signal] : [],
        })) },
    };
    const rows = studyH017BlueCandidates(base);
    expect(rows.map(x => x.first_touch)).toEqual([
      "TARGET_FIRST", "BOTH_SAME_M5", "STOP_FIRST", "UNRESOLVED",
    ]);
    expect(rows[0].crossings_at_open).toEqual([signal]);
    expect(rows[1].crossings_at_open).toEqual([]); // Not from candidate's own close.
    expect(visibleH017CandidateStudy(rows, null)).toEqual([]);
    expect(visibleH017CandidateStudy(rows, events[0].time_ms)).toEqual([]);
    expect(visibleH017CandidateStudy(rows, events[1].time_ms)).toMatchObject([
      { first_touch: "UNRESOLVED" },
    ]);
    expect(visibleH017CandidateStudy(rows, events[2].time_ms)).toMatchObject([
      { first_touch: "TARGET_FIRST", resolved_at_ms: events[2].time_ms },
    ]);
    expect(visibleH017CandidateStudy(rows, events[4].time_ms).map(x => x.first_touch))
      .toEqual(["TARGET_FIRST", "BOTH_SAME_M5", "STOP_FIRST"]);
    expect(visibleH017CandidateStudy(rows, events[5].time_ms).map(x => x.first_touch))
      .toEqual(["TARGET_FIRST", "BOTH_SAME_M5", "STOP_FIRST", "UNRESOLVED"]);
    expect(studyH017BlueCandidates({ ...base, mode: "STRATEGY" })).toEqual([]);
    expect(studyH017BlueCandidates({ ...base, dmi_5m: undefined })[0].crossings_at_open).toBeNull();
    expect(studyH017BlueCandidates({ ...base, h017_blue_risk_previews: [
      { ...candidate(1), risk_status: "RISK_BELOW_1R" },
    ] })).toEqual([]);
    // Mirror the FIRST-TOUCH policy for shorts without pretending intrabar order.
    const shortBars = events.map((e, i) => ({ ...e, candle: {
      ...e.candle, low: i === 2 ? 94 : 98, high: i === 3 ? 101 : 100.5,
    } }));
    const short = studyH017BlueCandidates({ ...base, events: shortBars,
      h017_blue_risk_previews: [candidate(1, "SHORT")] });
    expect(short[0].first_touch).toBe("TARGET_FIRST");
  });

  it("accepts strictly causal Wilder 5m DMI and hides future samples during playback", () => {
    const base = Date.UTC(2026, 9, 1);
    const events = Array.from({ length: 40 }, (_, i) => ({
      source: "SIMULATION", simulation_run_id: "adx_fixture", sequence: i + 1,
      kind: "CANDLE_CLOSED", time_ms: base + (i + 1) * 300_000,
      candle: {
        start_ms: base + i * 300_000, end_ms: base + (i + 1) * 300_000,
        open: "100", high: "102", low: "98", close: "101", volume: "10",
      },
    }));
    const points = events.map((event, i) => ({
      time_ms: event.time_ms,
      plus_di: i < 14 ? null : String(20 + i / 10),
      minus_di: i < 14 ? null : String(10 + i / 20),
      adx: i < 27 ? null : String(15 + i / 5),
    }));
    const archive = {
      source: "SIMULATION", simulation_run_id: "adx_fixture",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m",
      events,
      dmi_5m: {
        source: "SIMULATION", timeframe: "5m", di_length: 14, adx_smoothing: 14,
        points,
      },
    };
    const doc = parseReplayDocument(archive);
    expect(visibleDmi(doc, 0)).toEqual([]);
    expect(visibleDmi(doc, 14)).toHaveLength(14);
    expect(visibleDmi(doc, 14).at(-1)?.plus_di).toBeNull();
    expect(visibleDmi(doc, 15).at(-1)?.plus_di).toBeCloseTo(21.4);
    expect(visibleDmi(doc, 27).at(-1)?.adx).toBeNull();
    expect(visibleDmi(doc, 28).at(-1)?.adx).toBeCloseTo(20.4);
    expect(visibleDmi(doc, 40)).toHaveLength(40);
    expect(visibleDmi(doc, 999)).toHaveLength(40);
    expect(() => parseReplayDocument({
      ...archive, dmi_5m: { ...archive.dmi_5m,
        points: points.map((x, i) => i === 2 ? { ...x, adx: "42" } : x) },
    })).toThrow(/прогрева/);
    expect(() => parseReplayDocument({
      ...archive, dmi_5m: { ...archive.dmi_5m,
        points: points.map((x, i) => i === 29 ? { ...x, time_ms: x.time_ms + 300_000 } : x) },
    })).toThrow(/будущую/);
    expect(() => parseReplayDocument({
      ...archive, dmi_5m: { ...archive.dmi_5m,
        points: points.map((x, i) => i === 30 ? { ...x, minus_di: "NaN" } : x) },
    })).toThrow(/числовое поле/);
    expect(() => parseReplayDocument({
      ...archive, dmi_5m: { ...archive.dmi_5m,
        points: points.map((x, i) => i === 30 ? { ...x, plus_di: "101" } : x) },
    })).toThrow(/диапазона/);
    expect(parseReplayDocument({ ...archive, dmi_5m: undefined }).dmi_5m).toBeUndefined();
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
