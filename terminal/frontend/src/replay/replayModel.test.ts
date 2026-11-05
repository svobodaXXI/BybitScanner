import { describe, expect, it } from "vitest";
import { parseReplayDocument, syntheticReplay, simulationActionJournal, visibleReplay, visibleGeometry, visibleGeometryHistory, visiblePriorLevels, visiblePriorBreaks, visibleDmi, visibleObservations, visibleH017BlueRiskPreviews, studyH017BlueCandidates, visibleH017CandidateStudy, type ReplayDocument } from "./replayModel";

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
    expect(ending.candles).toHaveLength(64);
    expect(ending.exits).toHaveLength(1);
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
    expect(visibleGeometryHistory(doc, known(27) - 1)).toHaveLength(3);
    expect(visibleGeometryHistory(doc, known(27) - 1)
      .every(item => item.superseded_at_ms === undefined)).toBe(true);
    expect(visibleGeometryHistory(doc, known(35))[2].superseded_at_ms).toBe(known(27));
    expect(visibleGeometryHistory(doc, known(44)).map(item => item.from_ms)).toEqual(
      geometry.map(item => item.from_ms),
    );
  });

  it("replays purple priors at the second confirmed H1 touch and retains previous versions", () => {
    const demo = syntheticReplay();
    const events = demo.events.filter(e => e.kind === "CANDLE_CLOSED")
      .map((e, index) => ({ ...e, sequence: index + 1 }));
    const t0 = events[0].candle!.start_ms;
    const firstKnown = events[8].time_ms;
    const nextKnown = events[28].time_ms;
    const first = {
      kind: "MAIN_1H", side: "BEAR", available_at_ms: firstKnown,
      from_ms: t0, to_ms: events[3].candle!.start_ms,
      from_price: "120", to_price: "115", trend_version: firstKnown,
      classification: "UNVALIDATED_GEOMETRY_ONLY",
    };
    const next = {
      ...first, available_at_ms: nextKnown,
      from_ms: events[3].candle!.start_ms,
      to_ms: events[22].candle!.start_ms,
      from_price: "115", to_price: "110", trend_version: nextKnown,
    };
    const archive = {
      source: "SIMULATION", simulation_run_id: "purple_fixture",
      mode: "MARKET_ONLY", market_data_source: "BYBIT_PUBLIC_KLINE",
      symbol: "BTCUSDT", timeframe: "5m",
      events: events.map(e => ({ ...e, simulation_run_id: "purple_fixture" })),
      geometry: [first, next],
    };
    // A later confirmed touch alone cannot shift the purple level.
    const untouched = parseReplayDocument(archive);
    expect(visiblePriorLevels(untouched, nextKnown).map(p => p.price)).toEqual([115]);
    // The new lower LOW is closed AFTER the candidate touch and BEFORE
    // its confirmed availability. Only then may the prior move.
    const withNewLow = archive.events.map((event, index) => index === 26
      ? { ...event, candle: { ...event.candle!, low: 50 } } : event);
    const doc = parseReplayDocument({ ...archive, events: withNewLow });
    expect(visiblePriorLevels(doc, null)).toEqual([]);
    expect(visiblePriorLevels(doc, firstKnown - 1)).toEqual([]);
    expect(visiblePriorLevels(doc, firstKnown).map(p => p.price)).toEqual([115]);
    expect(visiblePriorLevels(doc, nextKnown - 1).map(p => p.price)).toEqual([115]);
    const after = visiblePriorLevels(doc, nextKnown);
    expect(after.map(p => p.price)).toEqual([115, 110]);
    expect(after[0].superseded_at_ms).toBe(nextKnown);
    expect(after[1].superseded_at_ms).toBeUndefined();
    expect(after[1].at_ms).toBe(events[22].candle!.start_ms);
    expect(visiblePriorLevels(doc, firstKnown)).toHaveLength(1); // rewind
    expect(visiblePriorLevels(demo, nextKnown)).toEqual([]); // no real-market prior in demo
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
