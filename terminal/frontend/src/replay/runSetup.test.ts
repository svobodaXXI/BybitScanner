import { describe, expect, it } from "vitest";
import {
  ALL_SELECTABLE, MIRROR_OPTIONS, clearAll, isAllSelected,
  onlyWedges, parseUtcMinute, presetEndInclusive, extendInclusiveWindow, parseRunCoordinates, selectAll,
  toggleMirror, toggleStrategy, validateInclusiveWindow,
  makeWedgeRunRequest, parseWedgeResult, parseWedgeStatus, runnableWedgeSelection,
} from "./runSetup";

describe("local one-symbol strategy setup (no trading)", () => {
  it("selects everything only once, including the entire Mirror bundle", () => {
    const all = selectAll();
    expect(isAllSelected(all)).toBe(true);
    expect(new Set(all.selected).size).toBe(ALL_SELECTABLE.length);
    expect(MIRROR_OPTIONS.every(option => all.selected.includes(option.id))).toBe(true);
    expect(isAllSelected(clearAll())).toBe(false);
  });
  it("enables Mirror defaults while preserving independent selections", () => {
    const trend = toggleStrategy(clearAll(), "H1_TREND", true);
    const mirror = toggleMirror(trend, true);
    expect(mirror.mirror).toBe(true);
    expect(mirror.selected).toContain("H1_TREND");
    expect(mirror.selected).toContain("WEDGE_RISING");
    expect(mirror.selected).toContain("WEDGE_FALLING");
    expect(mirror.selected).toContain("IKIGAI_BOX");
    const withoutBox = toggleStrategy(mirror, "IKIGAI_BOX", false);
    expect(withoutBox.mirror).toBe(true);
    expect(withoutBox.selected).not.toContain("IKIGAI_BOX");
    expect(toggleMirror(withoutBox, false).selected).toEqual(["H1_TREND"]);
  });
  it("lets owner isolate wedges without activating Mirror or other patterns", () => {
    expect(onlyWedges()).toEqual({
      mirror: false, selected: ["WEDGE_RISING", "WEDGE_FALLING"],
    });
  });
  it("applies inclusive last minute for day, week, 30 and 90 days", () => {
    const start = "2026-10-01T12:34";
    const cases = [
      ["DAY", "2026-10-02T12:33", 1440],
      ["WEEK", "2026-10-08T12:33", 10080],
      ["MONTH", "2026-10-31T12:33", 43200],
      ["THREE_MONTHS", "2026-12-30T12:33", 129600],
    ] as const;
    for (const [preset, expectedEnd, minutes] of cases) {
      const end = presetEndInclusive(start, preset);
      expect(end).toBe(expectedEnd);
      const window = validateInclusiveWindow(start, end);
      expect(window.minutes).toBe(minutes);
      expect(window.endExclusiveMs).toBe(parseUtcMinute(end) + 60_000);
    }
  });
  it("extends the current inclusive UTC range cumulatively, never resets its start", () => {
    const start = "2026-09-11T00:00";
    let end = "2026-09-11T23:59";
    end = extendInclusiveWindow(start, end, "HOUR");
    expect(end).toBe("2026-09-12T00:59");
    end = extendInclusiveWindow(start, end, "DAY");
    expect(end).toBe("2026-09-13T00:59");
    end = extendInclusiveWindow(start, end, "WEEK");
    expect(end).toBe("2026-09-20T00:59");
    end = extendInclusiveWindow(start, end, "MONTH");
    expect(end).toBe("2026-10-20T00:59");
    expect(validateInclusiveWindow(start, end).minutes).toBe(39 * 1440 + 60);
    expect(() => extendInclusiveWindow(start, presetEndInclusive(start, "THREE_MONTHS"), "HOUR"))
      .toThrow(/90 дней/);
  });
  it("parses pasted ticker and inclusive UTC dates without timezone guessing", () => {
    expect(parseRunCoordinates("XRPUSDT | 2026-09-11T00:00 | 2026-09-11T23:59")).toEqual({
      symbol: "XRPUSDT", start_utc: "2026-09-11T00:00",
      end_utc_inclusive: "2026-09-11T23:59",
    });
    for (const value of [
      "PAPER | 2026-09-11T00:00 | 2026-09-11T23:59",
      "XRPUSDT | 2026-02-30T00:00 | 2026-03-01T23:59",
      "XRPUSDT | 2026-09-12T00:00 | 2026-09-11T23:59",
      "XRPUSDT | 2026-09-11 | 2026-09-12",
      "XRPUSDT | 2026-01-01T00:00 | 2026-04-02T00:00",
    ]) expect(() => parseRunCoordinates(value)).toThrow();
  });
  it("handles year and leap-day boundaries without local timezone dependence", () => {
    expect(presetEndInclusive("2024-02-29T23:59", "DAY")).toBe("2024-03-01T23:58");
    expect(presetEndInclusive("2026-12-31T23:59", "WEEK")).toBe("2027-01-07T23:58");
    expect(validateInclusiveWindow("2026-10-01T00:00", "2026-10-01T00:00").minutes).toBe(1);
  });
  it("rejects invalid, reversed or non-minute boundaries", () => {
    expect(() => parseUtcMinute("2026-02-30T00:00")).toThrow();
    expect(() => parseUtcMinute("2026-02-28T24:00")).toThrow();
    expect(() => parseUtcMinute("2026-02-28T11:00:00")).toThrow();
    expect(() => validateInclusiveWindow("2026-10-02T00:00", "2026-10-01T23:59")).toThrow();
  });
  it("submits one or both actual wedges, not Mirror/all/other unsupported strategies", () => {
    expect(runnableWedgeSelection(onlyWedges())).toBe(true);
    expect(runnableWedgeSelection(clearAll())).toBe(false);
    expect(runnableWedgeSelection(selectAll())).toBe(false);
    expect(runnableWedgeSelection(toggleStrategy(clearAll(), "WEDGE_RISING", true))).toBe(true);
    const req = makeWedgeRunRequest(
      onlyWedges(), "btcusdt", "2026-10-01T12:34", "2026-10-08T12:33", "1000",
    );
    expect(req).toEqual({
      symbol: "BTCUSDT", start_utc: "2026-10-01T12:34",
      end_utc_inclusive: "2026-10-08T12:33",
      selected_strategies: ["WEDGE_RISING", "WEDGE_FALLING"],
      initial_balance: "1000",
    });
    expect(() => makeWedgeRunRequest(
      selectAll(), "BTCUSDT", "2026-10-01T12:34", "2026-10-08T12:33", "1000",
    )).toThrow(/только/);
    expect(() => makeWedgeRunRequest(
      onlyWedges(), "BTCUSDT", "2026-10-01T00:00", "2026-12-31T00:00", "1000",
    )).toThrow(/90/);
    expect(() => makeWedgeRunRequest(
      onlyWedges(), "BTCUSDT", "2026-10-01T00:00", "2026-10-01T00:00", "0",
    )).toThrow(/депозит/);
  });
  it("never trusts non-SIMULATION responses or fabricated PnL", () => {
    const status = {
      namespace: "SIMULATION", can_attempt: true,
      wedge_engine_available: true, python_dependencies_available: true,
      archive_files_present: true, wedge_risk_profile_present: true,
    };
    expect(parseWedgeStatus(status)).toEqual(status);
    const withArchive = { ...status, archive_hint: {
      symbol: "XRPUSDT", start_utc: "2026-09-11T00:00",
      end_utc_inclusive: "2026-09-11T23:59",
    } };
    expect(parseWedgeStatus(withArchive).archive_hint?.symbol).toBe("XRPUSDT");
    expect(() => parseWedgeStatus({ ...status, archive_hint: {
      ...withArchive.archive_hint, end_utc_inclusive: "2026-09-12T23:59",
    } })).toThrow();
    expect(() => parseWedgeStatus({ ...status, archive_hint: {
      ...withArchive.archive_hint, symbol: "../../PAPER",
    } })).toThrow();
    expect(() => parseWedgeStatus({ ...status, namespace: "PAPER" })).toThrow();
    expect(() => parseWedgeStatus({ ...status, can_attempt: "yes" })).toThrow();
    const report = {
      namespace: "SIMULATION",
      scenario_type: "ORIGINAL_WEDGE_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION",
      risk_terms_status: "EXPLICIT_RESEARCH_ASSUMPTIONS_NOT_EXCHANGE_VERIFIED",
      symbol: "BTCUSDT", source_id: "BYBIT_PUBLIC_TRADES_RANGE_test",
      requested_minutes: 2, scanner_wedge_observations: 0,
      robot_retests_in_period: 0, submitted_protected_limits: 0,
      virtual_fills: 0, stop_exits: 0, take_exits: 0,
      realized_net_pnl: "0", unrealized_pnl: "0", total_net_pnl: "0",
      total_fees: "0", return_percent: "0", max_drawdown_percent: "0",
    };
    expect(parseWedgeResult(report).requested_minutes).toBe(2);
    expect(() => parseWedgeResult({ ...report, namespace: "PAPER" })).toThrow();
    expect(() => parseWedgeResult({ ...report, scenario_type: "EXPLICIT_TEST_ORDERS_NOT_STRATEGY" })).toThrow();
    expect(() => parseWedgeResult({ ...report, virtual_fills: -1 })).toThrow();
    expect(() => parseWedgeResult({ ...report, total_net_pnl: 900 })).toThrow();
  });

});
